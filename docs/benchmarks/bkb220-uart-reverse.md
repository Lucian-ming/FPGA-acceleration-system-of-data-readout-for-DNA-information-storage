# BKB220 PS UART 反向（PC→PS）实测（2026-10-14）

**结论：通过。** PC 往 `/dev/ttyUSB2` 发 31 字节，JTAG 从 UART0 的 **RX FIFO** 读回，
**逐字节相同**，且期间无溢出（`RXOVR` 未置位）。

至此这路串口**两个方向都已实测**：

| 方向 | 状态 | 出处 |
| --- | --- | --- |
| **PS→PC**（板子打印，PC 收） | ✅ 早已实测 | `docs/09-evidence-ledger.md`（JTAG 写 UART0 TX FIFO，PC 收到 `BKB220-UART0-1..8` 共 128 B） |
| **PC→PS**（PC 发，板子收） | ✅ **本次实测** | 本页 |

---

## 1. 测法与依据

| 项 | 值 | 出处 |
| --- | --- | --- |
| UART0 基地址 | `0xE0000000` | 制品包 BSP 的 `xparameters.h`：`XPAR_PS7_UART_0_BASEADDR` |
| 通道状态寄存器 | `+0x2C` | `xuartps_hw.h` 的 `XUARTPS_SR_OFFSET` |
| **`RXEMPTY`** | **bit 1（`0x2`）** | `xuartps_hw.h`：`XUARTPS_SR_RXEMPTY 0x00000002` |
| `RXFULL` / `TXEMPTY` | bit 2（`0x4`）/ bit 3（`0x8`） | 同上 |
| `RXOVR` | bit 0（`0x1`） | `XUARTPS_SR_RXOVR 0x00000001` |
| FIFO 数据口 | `+0x30` | `XUARTPS_FIFO_OFFSET`；**读 = 弹 RX FIFO** |
| 串口参数 | 115200 8N1 raw | — |

> ⚠️ **第一次我把 `RXEMPTY` 猜成了 bit 2**，导致清空循环一直读到 80 个 `0x00` 才停。
> **位定义必须查 `xuartps_hw.h`，不能凭印象**——这条值得记下来。

## 2. 实测过程与原始输出

**① 初态（清空后）**

```
BEFORE_CHANNEL_STS: 0x0000000A     # bit1 RXEMPTY=1、bit3 TXEMPTY=1 ⇒ RX FIFO 空
```

**② PC 发送**（`stty -F /dev/ttyUSB2 115200 cs8 -cstopb -parenb -echo raw` 后写入）

```
UART0RX-REVERSE-TEST-0123456789     # 31 字节
```

**③ JTAG 读回**

```
AFTER_SEND_STS: 0x00000008          # bit1 RXEMPTY=0 ⇒ FIFO 里有数据
RECEIVED_BYTES: 31
RECEIVED_HEX: 55 41 52 54 30 52 58 2D 52 45 56 45 52 53 45 2D 54 45 53 54 2D 30 31 32 33 34 35 36 37 38 39
```

`RECEIVED_HEX` 解码 = `UART0RX-REVERSE-TEST-0123456789`，**与发送内容逐字节相同**；
状态字里 **`RXOVR`（bit0）= 0**，未溢出。

## 3. 为什么不用改固件、也不用重烧

- 板子跑的是本次实测前**已经烧好**的固件（来自同一次会话的 G3 判据轮）。
- 该固件只用 `xil_printf`（**只写 TX**），**从不读 RX** ⇒ 发进来的字节会**原样积在 RX FIFO**里，
  正好被 JTAG 读出来。
- 所以这是**对现有制品的被动观测**，不是"改了固件才通过"。

## 4. ⚠️ 边界（引用本页时必须一起说）

1. **这证明的是 PS 的 UART0 收得到字节**，即**硬件通路与引脚映射正确**；
   **不证明**板上跑着什么读 UART 的协议——**当前固件根本不消费 RX**，
   本项目的数据通道是**以太网 TCP**，串口**只用于打日志**。
2. 因此本项是**硬件完备性**证据（串口两个方向都通），**不是功能依赖项**。
   若将来要用串口当备用命令通道，还需要在固件里真的实现读取与解析——**那是另一件事，未做**。
3. 只测了**短包**（31 字节，未触及 64 字节 FIFO 上限）；**长包/连续流的流控与溢出行为未测**。
4. 未测波特率容差、奇偶校验、流控（RTS/CTS）等参数组合。
