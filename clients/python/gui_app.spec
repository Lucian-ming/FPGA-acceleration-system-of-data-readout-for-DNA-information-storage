# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['gui_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('resources/R5_6_LDPC_hard_decoder.exe', 'resources'),
        ('resources/dvb_s2_r5_6.pchk', 'resources'),
        ('resources/permutation64800', 'resources'),
        # LDPC 解码器是 MinGW 构建，缺这三个 DLL 会静默失败（无输出、退出码仍为 0）
        ('resources/libstdc++-6.dll', 'resources'),
        ('resources/libgcc_s_seh-1.dll', 'resources'),
        ('resources/libwinpthread-1.dll', 'resources'),
        # 注意：绝不要在这里打包 dec_input.txt 或任何参考结果。
        # 历史版本曾打包一份正确的 dec_input.txt，使 EXE 能绕过 FPGA 直接出图。
        # dec_input.txt 必须由本次运行的板端回传数据生成。
    ],
    hiddenimports=['PIL.ImageTk'],
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
