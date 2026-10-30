"""Small Windows desktop front end; portable engine remains usable without Tk."""
import json,queue,sys,threading,tkinter as tk
from tkinter import ttk,filedialog,messagebox
from pathlib import Path
from patcher import Manager,locate_games,BASE

def main():
    root=tk.Tk()
    if '--smoke-test' in sys.argv:root.withdraw()
    root.title("King's Quest 한국어 시험 패치 v0.1.0");root.geometry('820x570');root.minsize(700,480)
    root.option_add('*Font','맑은고딕 10');events=queue.Queue();busy=False
    frame=ttk.Frame(root,padding=16);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='챕터 1~5 · 에필로그 한국어 시험 패치',font=('맑은고딕',16,'bold')).pack(anchor='w')
    ttk.Label(frame,text='전체 초벌 번역입니다. 영어 음성은 유지됩니다. 게임을 종료한 뒤 설치하세요.').pack(anchor='w',pady=(5,12))
    line=ttk.Frame(frame);line.pack(fill='x');path=tk.StringVar()
    ttk.Entry(line,textvariable=path).pack(side='left',fill='x',expand=True)
    def browse():
        chosen=filedialog.askdirectory(title="GrahamsGame 폴더가 들어 있는 King's Quest 설치 폴더 선택")
        if chosen:path.set(chosen)
    ttk.Button(line,text='게임 폴더 선택',command=browse).pack(side='left',padx=(8,0))
    games=locate_games()
    if games:path.set(str(games[0]))
    ttk.Label(frame,text='예: Steam → 게임 속성 → 설치된 파일 → 찾아보기에서 확인한 폴더').pack(anchor='w',pady=(4,12))
    buttons=ttk.Frame(frame);buttons.pack(fill='x');controls=[]
    output=tk.Text(frame,wrap='word',height=17);output.pack(fill='both',expand=True,pady=(12,8))
    scroll=ttk.Scrollbar(output,command=output.yview);scroll.pack(side='right',fill='y');output.configure(yscrollcommand=scroll.set)
    output.insert('end','설치된 챕터를 자동으로 선택합니다. 설치 전 전체 파일을 검사하고 원본을 백업합니다.\nDroidDeck은 동봉 README의 Linux/ARM64 사용법을 따르세요.\n')
    progress=ttk.Progressbar(frame,mode='indeterminate');progress.pack(fill='x')
    def append(text):output.insert('end',text+'\n');output.see('end')
    def run(action):
        nonlocal busy
        if busy:return
        game=path.get().strip()
        if not game:messagebox.showerror('게임 폴더 필요','게임 설치 폴더를 선택하세요.');return
        busy=True;progress.start();[b.configure(state='disabled') for b in controls]
        def worker():
            try:
                mgr=Manager(game,BASE,lambda s:events.put(('log',s)))
                if action=='verify':
                    results=mgr.scan();counts={k:sum(r['status']==k for r in results) for k in ('original','patched','missing','different')}
                    events.put(('log',json.dumps(counts,ensure_ascii=False)))
                    for r in results:
                        if r['status'] in ('missing','different'):events.put(('log',r['status']+': '+r['path']))
                    if counts['missing'] or counts['different']:raise ValueError('다른 버전 또는 누락 파일이 있습니다. 게임 파일은 변경하지 않았습니다.')
                else:getattr(mgr,action)()
                events.put(('done','검사가 끝났습니다.' if action=='verify' else '작업이 완료됐습니다.'))
            except Exception as exc:events.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()
    for text,action in [('설치 상태 검사','verify'),('한글 패치 설치','install'),('원본으로 복원','restore'),('중단된 작업 복구','recover')]:
        b=ttk.Button(buttons,text=text,command=lambda a=action:run(a));b.pack(side='left',padx=(0,7));controls.append(b)
    def save_log():
        target=filedialog.asksaveasfilename(defaultextension='.txt',initialfile='KingsQuest-KO-test-log.txt')
        if target:Path(target).write_text(output.get('1.0','end'),encoding='utf-8')
    ttk.Button(frame,text='시험 기록 저장',command=save_log).pack(anchor='e',pady=(8,0))
    def tick():
        nonlocal busy
        while not events.empty():
            kind,text=events.get();append(text)
            if kind in ('done','error'):
                busy=False;progress.stop();[b.configure(state='normal') for b in controls]
                if kind=='error':messagebox.showerror('작업 중단',text)
        root.after(100,tick)
    def close():
        if busy:messagebox.showinfo('작업 중','파일 작업이 끝난 뒤 닫아 주세요.');return
        root.destroy()
    root.protocol('WM_DELETE_WINDOW',close)
    if '--smoke-test' in sys.argv:
        root.update_idletasks();assert len(controls)==4;root.destroy();return
    tick();root.mainloop()

if __name__=='__main__':main()
