# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

CLIENT_DIR = Path(SPECPATH)
RESOURCE_DIR = CLIENT_DIR / 'resources'


a = Analysis(
    [str(CLIENT_DIR / 'gui_app.py')],
    pathex=[str(CLIENT_DIR)],
    binaries=[],
    datas=[
        (str(RESOURCE_DIR / 'R5_6_LDPC_hard_decoder.exe'), 'resources'),
        (str(RESOURCE_DIR / 'dvb_s2_r5_6.pchk'), 'resources'),
        (str(RESOURCE_DIR / 'permutation64800'), 'resources'),
        (str(RESOURCE_DIR / 'SOURCES.json'), 'resources'),
        # LDPC 解码器是 MinGW 构建，缺这三个 DLL 会静默失败（无输出、退出码仍为 0）
        (str(RESOURCE_DIR / 'libstdc++-6.dll'), 'resources'),
        (str(RESOURCE_DIR / 'libgcc_s_seh-1.dll'), 'resources'),
        (str(RESOURCE_DIR / 'libwinpthread-1.dll'), 'resources'),
        # 注意：绝不要在这里打包 dec_input.txt 或任何参考结果。
        # 历史版本曾打包一份正确的 dec_input.txt，使 EXE 能绕过 FPGA 直接出图。
        # dec_input.txt 必须由本次运行的板端回传数据生成。
        # Windows 当前没有 c_ldpc.dll，因此绝不打包 Linux 的 libc_ldpc.so。
    ],
    hiddenimports=['PIL.ImageTk', 'c_ldpc', 'ctypes'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='gui_app',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
