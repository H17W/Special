from app.core.database import db
def add(user_id,kind,path,caption='',category='general'):
 import time
 db.run('INSERT INTO storage_items(user_id,kind,path,caption,category,created_at) VALUES(?,?,?,?,?,?)',(user_id,kind,path,caption,category,int(time.time())))
def search(term,limit=30):
 term=f'%{term}%'; return db.all('SELECT * FROM storage_items WHERE caption LIKE ? OR category LIKE ? ORDER BY created_at DESC LIMIT ?',(term,term,limit))
