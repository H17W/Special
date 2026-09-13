from .database import db

def audit(uid,action,detail=''): db.log(uid,action,detail)
