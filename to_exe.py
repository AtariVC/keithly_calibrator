from pathlib import Path
import os
# from kpa_async_pyqt_client.utils import cwd
# from kpa_frames.utils import cwd as frames_cwd
# from qissuereporter.utils import exe_cwd


def to_exe() -> None:
    # icon: str = '--icon ' + str(cwd().joinpath('assets', 'settings.ico'))
    flags: list[str] = ["--name Keithly Calibrator", "--console", "--onefile",
                        "--clean", "--noconfirm"]
    main_path: str = str(Path(__file__).parent.joinpath('__main__.py'))
    ui_paths: list[str] = ['--add-data ' + str(f"\"{file};.\"")
                           for file in Path(__file__).parent.glob("*.ui")]
    modules: str = '--add-data ' + f'\"{str(Path(__file__).parent)}\\modules;modules\"'
    src: str = '-- add-data ' + f'\"{str(Path(__file__).parent)}\\src;src\"'
    custom: str = '-- add-data ' + f'\"{str(Path(__file__).parent)}\\custom;custom\"'
    # pyqt_client_path: str = '--add-data ' + f'\"{str(cwd())};kpa_async_pyqt_client\"'
    # frames: str = '--add-data ' + f'\"{str(frames_cwd())};kpa_frames\"'
    # issue_reporter = f'--add-data \"{exe_cwd().parent / "qissuereporter"};qissuereporter\"'


    destination: str = '--distpath ' + str(Path.cwd())
    to_exe_cmd: str = ' '.join(["pyinstaller", main_path,
                                *flags,
                                destination,
                                modules,
                                src,
                                custom,
                                # icon,
                                # pyqt_client_path,
                                # issue_reporter,
                                # frames,
                                # ba_kv_path,
                                *ui_paths,
                                ])
    os.system(to_exe_cmd)
    for flag in to_exe_cmd.split('--'):
        print(f'--{flag}')

if __name__ == '__main__':
    # print(cwd())
    to_exe()
    # print(f'\"{str(Path(__file__).parent)}\\modules;modules\"')