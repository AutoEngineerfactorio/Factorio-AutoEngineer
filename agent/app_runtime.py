"""Paths and child commands shared by source and one-folder Windows builds."""
import os
from pathlib import Path
import sys


def data_root():
    if os.environ.get('AUTOENGINEER_HOME'):
        return Path(os.environ['AUTOENGINEER_HOME']).resolve()
    return Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]


def component_command(name):
    if name not in ('dashboard','dashboard_observer','supervised_agent','backend_check'):
        raise ValueError('Unknown application component')
    if getattr(sys,'frozen',False):
        return [str(Path(sys.executable).with_name('AutoEngineerWorker.exe')),'--component',name]
    script='launcher_app.py' if name in ('dashboard','backend_check') else name+'.py'
    command=[sys.executable,'-u',str(Path(__file__).with_name(script))]
    return command+['--component',name] if name in ('dashboard','backend_check') else command
