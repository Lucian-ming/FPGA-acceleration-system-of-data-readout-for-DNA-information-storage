 🧬 Vitis DNA Accelerator — Zynq Pipeline Project

## 📖 项目简介
本项目基于 **Xilinx Zynq-7000 (XC7Z010)** 平台开发，实现了三阶段硬件加速流水线系统：
1. **DNA Accelerator Core** — 数据预处理  
2. **Differential Voter Core** — 加权投票计算  
3. **Desparsification Decoder Core** — 稀疏解码重构  
4. **AXI DMA** — PS 与 PL 间数据搬运  
5. **lwIP Echo Server** — TCP 网络服务端

---

## 🧰 目录结构
```
vitis-dna-accelerator/
├─ hw/                 # PL 工程
│  ├─ ip/              # 三个 IP 核
│  ├─ constr/          # 约束文件
│  └─ scripts/         # 构建 Tcl 脚本
├─ sw/                 # PS 软件
│  ├─ app/             # lwIP 应用
│  ├─ linker/          # 链接脚本
│  └─ scripts/         # XSCT 脚本
├─ clients/python/     # 上位机 TCP 客户端
├─ docs/               # 技术说明
├─ LICENSE
├─ THIRD_PARTY_NOTICES.md
└─ .gitignore
```

---

## ⚙️ 环境要求
- Vivado / Vitis 版本：2022.2
- 硬件平台：Zynq-7000 (xc7z010clg400-1)
- Python 依赖：`pip install -r clients/python/requirements.txt`

---

## 🧩 一键复现
```bash
vivado -mode batch -source hw/scripts/build.tcl
xsct sw/scripts/create_vitis.tcl
```

生成：  
- `hw/build/export/*.xsa`  
- `sw/workspace/dna_lwip_app/Debug/dna_lwip_app.elf`

---

## 🚀 运行
1. 烧录 `.bit` 与 `.elf`
2. 设置 IP = 192.168.1.10
3. 运行客户端：
```bash
cd clients/python
python client.py --ip 192.168.1.10 --port 7
```


© 2025 Vitis DNA Accelerator Project
