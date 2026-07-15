import sqlite3, hashlib, os

db = sqlite3.connect('/data/database/platform.sqlite3')
rows = db.execute('SELECT version,active FROM releases').fetchall()
print('Current:', rows)

exe_path = '/app/downloads/VD开播助手-V2.8.1.exe'
if os.path.exists(exe_path):
    h = hashlib.sha256(open(exe_path, 'rb').read()).hexdigest()
    s = os.path.getsize(exe_path)
    print('SHA256:', h[:16], 'Size:', s)
    db.execute("INSERT OR REPLACE INTO releases(version,title,notes,filename,sha256,file_size,channel,active,created_at) VALUES('2.8.1','VD开播助手 V2.8.1','新版UI品牌升级','VD开播助手-V2.8.1.exe',?,?,'stable',1,datetime('now'))", (h, s))
    db.execute("UPDATE releases SET active=0 WHERE version!='2.8.1'")
    db.commit()
    print('DB updated')
else:
    print('EXE not found')
    # try to find it
    for root, dirs, files in os.walk('/app'):
        for f in files:
            if '2.8.1' in f:
                print('Found:', os.path.join(root, f))

rows = db.execute('SELECT version,active FROM releases').fetchall()
print('After:', rows)
db.close()