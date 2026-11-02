#ifndef __WM_EXPAND_H__
#define __WM_EXPAND_H__
/******************************************************************************
 * wm_expand.h — 水印展开的纯计算部分
 *
 * 刻意不依赖任何 Xilinx 头文件，这样同一份代码既能编进 PS 固件，
 * 也能在主机上用黄金向量做单元测试（tools/test_wm_expand.c）。
 * 水印的位序和区域几何一旦错了，Stage1 的比对结果就全无意义，
 * 而这种错误在板上极难定位——必须在主机侧钉死。
 *
 * 数据契约（docs/02-data-contract.md）：
 *   打包水印按「码流顺序 + 字节内 LSB-first」，共 2*SYMBOLS 位
 *       bit[k]    = (wm[k>>3] >> (k&7)) & 1
 *   位平面布局：前 SYMBOLS 位是每个符号的高位，后 SYMBOLS 位是低位
 *       symbol[i] = (bit[i] << 1) | bit[SYMBOLS + i]
 *   区域 lc 覆盖符号 [lc*STRIDE, lc*STRIDE + REF_LEN)，区域间重叠 READ_BPS
 ******************************************************************************/

/* 取打包水印里第 idx 个符号（0..3） */
static inline unsigned wm_symbol_at(const unsigned char *wm,
                                    unsigned idx, unsigned symbols)
{
    unsigned k_hi = idx;
    unsigned k_lo = symbols + idx;
    unsigned hi = (unsigned)((wm[k_hi >> 3] >> (k_hi & 7u)) & 1u);
    unsigned lo = (unsigned)((wm[k_lo >> 3] >> (k_lo & 7u)) & 1u);
    return (hi << 1) | lo;
}

/* 区域 lc 的第 row 个符号；越界补 0 */
static inline unsigned wm_region_symbol(const unsigned char *wm,
                                        unsigned lc, unsigned row,
                                        unsigned stride, unsigned symbols)
{
    unsigned idx = lc * stride + row;
    if (idx >= symbols) {
        return 0u;
    }
    return wm_symbol_at(wm, idx, symbols);
}

#endif /* __WM_EXPAND_H__ */
