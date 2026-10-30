"""BSDIFF40 and King's Quest UE3 codec; patch application needs no pip packages."""
import base64,bz2,ctypes,ctypes.util,hashlib,struct,zlib

def sha(data):return hashlib.sha256(data).hexdigest()

def package_raw(data):
    if data[:4]!=b'\xc1\x83\x2a\x9e' or struct.unpack_from('<I',data,4)[0]!=861:raise ValueError('Unsupported UE3 package')
    compression,count=struct.unpack_from('<II',data,109)
    if not 0<count<4096:raise ValueError('Unsupported chunk count')
    chunks=[struct.unpack_from('<4I',data,117+i*16) for i in range(count)]
    length=max(c[0]+c[1] for c in chunks)
    if length>512*1024*1024:raise ValueError('Package exceeds memory limit')
    result=bytearray(length);result[:chunks[0][0]]=data[:chunks[0][0]]
    for virtual,size,offset,packed_size in chunks:
        magic,block_size,total_packed,total_raw=struct.unpack_from('<4I',data,offset)
        if magic!=0x9e2a83c1 or total_raw!=size or not 0<block_size<=16*1024*1024:raise ValueError('Invalid UE3 chunk')
        n=(size+block_size-1)//block_size
        lengths=[struct.unpack_from('<II',data,offset+16+i*8) for i in range(n)]
        pos=offset+16+n*8;out=bytearray()
        for packed,unpacked in lengths:
            block=data[pos:pos+packed]
            if compression==1:decoded=zlib.decompress(block)
            elif compression==2:decoded=lzo_decompress(block,unpacked)
            else:raise ValueError('Unsupported UE3 compression')
            if len(decoded)!=unpacked:raise ValueError('UE3 block length mismatch')
            out.extend(decoded);pos+=packed
        if len(out)!=size or pos!=offset+packed_size:raise ValueError('UE3 chunk length mismatch')
        result[virtual:virtual+size]=out
    return bytes(result)

def lzo_decompress(block,size):
    try:
        import lzokay
        return lzokay.decompress(block,size)
    except ImportError:pass
    name=ctypes.util.find_library('lzo2')
    if not name:raise RuntimeError('liblzo2 is required. Ubuntu/DroidDeck terminal: sudo apt install liblzo2-2')
    lib=ctypes.CDLL(name);fn=lib.lzo1x_decompress_safe
    fn.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.POINTER(ctypes.c_size_t),ctypes.c_void_p];fn.restype=ctypes.c_int
    source=ctypes.create_string_buffer(block);dest=ctypes.create_string_buffer(size);length=ctypes.c_size_t(size)
    code=fn(source,len(block),dest,ctypes.byref(length),None)
    if code or length.value!=size:raise ValueError('LZO decompression failed')
    return dest.raw[:length.value]

def semantic_sha(raw):
    # The expanded first block starts at virtual offset 129 in these packages;
    # it overlaps the physical compression table. Do not treat its name-table
    # bytes as chunk metadata or blank them out.
    virtual=struct.unpack_from('<I',raw,117)[0]
    if not 117<=virtual<=65536:raise ValueError('Unexpected virtual header size')
    return sha(raw[:109]+bytes(virtual-109)+raw[virtual:])

def package_compress(raw,header):
    count=struct.unpack_from('<I',header,113)[0]
    chunks=[struct.unpack_from('<4I',header,117+i*16) for i in range(count)]
    output=bytearray(header)
    if len(output)<117+count*16:raise ValueError('Missing physical package header')
    struct.pack_into('<I',output,109,1)
    for i,(virtual,size,offset,packed_size) in enumerate(chunks):
        if i==count-1:size=len(raw)-virtual
        blocks=[raw[j:min(j+131072,virtual+size)] for j in range(virtual,virtual+size,131072)]
        packed=[zlib.compress(block) for block in blocks]
        chunk=struct.pack('<4I',0x9e2a83c1,131072,sum(map(len,packed)),size)
        chunk+=b''.join(struct.pack('<II',len(a),len(b)) for a,b in zip(packed,blocks))+b''.join(packed)
        struct.pack_into('<4I',output,117+i*16,virtual,size,len(output),len(chunk));output.extend(chunk)
    return bytes(output)

def signed64(data):
    value=int.from_bytes(data,'little');return -(value&((1<<63)-1)) if value>>63 else value

def bspatch(old,patch):
    if patch[:8]!=b'BSDIFF40' or len(patch)<32:raise ValueError('Invalid delta header')
    cl,dl,size=[signed64(patch[i:i+8]) for i in (8,16,24)]
    if min(cl,dl,size)<0 or size>512*1024*1024 or 32+cl+dl>len(patch):raise ValueError('Invalid delta size')
    control=bz2.decompress(patch[32:32+cl]);diff=bz2.decompress(patch[32+cl:32+cl+dl]);extra=bz2.decompress(patch[32+cl+dl:])
    result=bytearray(size);cp=dp=ep=op=np=0
    while np<size:
        if cp+24>len(control):raise ValueError('Truncated delta controls')
        x,y,z=[signed64(control[cp+i:cp+i+8]) for i in (0,8,16)];cp+=24
        if x<0 or y<0 or np+x+y>size or dp+x>len(diff) or ep+y>len(extra):raise ValueError('Invalid delta control')
        result[np:np+x]=diff[dp:dp+x]
        lo=max(0,-op);hi=min(x,len(old)-op)
        # Chunked addition bounds temporary memory and accepts negative old positions.
        for start in range(lo,max(lo,hi),65536):
            end=min(hi,start+65536)
            result[np+start:np+end]=bytes((a+b)&255 for a,b in zip(diff[dp+start:dp+end],old[op+start:op+end]))
        np+=x;op+=x;dp+=x
        result[np:np+y]=extra[ep:ep+y];np+=y;ep+=y;op+=z
    if cp!=len(control) or dp!=len(diff) or ep!=len(extra):raise ValueError('Unused delta data')
    return bytes(result)

def apply_delta(original,delta,record):
    if sha(original)!=record['original_sha256']:raise ValueError('Game version/hash mismatch: '+record['path'])
    if sha(delta)!=record['delta_sha256']:raise ValueError('Damaged patch payload')
    if record['codec']=='bsdiff40':result=bspatch(original,delta)
    elif record['codec']=='ue3-raw-bsdiff40-zlib':
        raw=bspatch(package_raw(original),delta)
        if semantic_sha(raw)!=record['target_semantic_sha256']:raise ValueError('Decoded package delta mismatch')
        result=package_compress(raw,base64.b64decode(record['target_header_b64'],validate=True))
    else:raise ValueError('Unknown patch codec')
    if sha(result)!=record['target_sha256']:
        # zlib versions may produce different bytes; all decompressed package bytes
        # except physical compression offsets must still match exactly.
        if record['codec']!='ue3-raw-bsdiff40-zlib' or semantic_sha(package_raw(result))!=record['target_semantic_sha256']:raise ValueError('Patched file verification failed')
    return result
