from pathlib import Path
root=Path(SPECPATH).parent
agent=root/'agent'
a=Analysis([str(agent/'launcher_app.py')],pathex=[str(agent)],
 hiddenimports=['autoengineer_dashboard','dashboard_observer','supervised_agent','mcp.client.stdio','psutil'],
 binaries=[],datas=[],hookspath=[],hooksconfig={},runtime_hooks=[],excludes=[])
pyz=PYZ(a.pure)
launcher=EXE(pyz,a.scripts,[],exclude_binaries=True,name='AutoEngineer',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=False)
worker=EXE(pyz,a.scripts,[],exclude_binaries=True,name='AutoEngineerWorker',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=True)
coll=COLLECT(launcher,worker,a.binaries,a.datas,strip=False,upx=False,name='AutoEngineer')
