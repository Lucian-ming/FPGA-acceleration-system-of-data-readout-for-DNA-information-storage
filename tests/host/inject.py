#!/usr/bin/env python3
"""对 echo.c 的一份**临时副本**做定点改动，用来自证轨迹判据「能失败」。

判据纪律（tests/host/README.md的判据鉴别力）：一条不会失败的判据，通过了也没有信息量。所以每个注入
都模拟一次「拆分时顺手整理掉了不该动的东西」，轨迹判据必须因此变红。

仓库里的 sw/app/echo.c 一个字节都不会被改：改的是 --out 指定的副本。
注入点找不到时**报错退出**——那说明 echo.c 变了，注入点要跟着更新，
而不是让自证悄悄变成空操作。
"""
import sys, argparse

INJECTIONS = {
    "b27-start-clear": (
        "复刻 B27：Decoder START=1 之后再写一次 START=0（当年那句「脉冲结束」）",
        '''	        write_reg32(DECODER_BASEADDR, DECODER_REG_START, 0x01);
	        usleep(100);  /* 只是让 START 在 M 域被采样，期间不再碰这个寄存器 */''',
        '''	        write_reg32(DECODER_BASEADDR, DECODER_REG_START, 0x01);
	        usleep(100);
	        write_reg32(DECODER_BASEADDR, DECODER_REG_START, 0x00);''',
    ),
    "dec-beats-order": (
        "把 Decoder 配置里 OUT_BEATS / IN_BEATS 的写入顺序对调（注释明说「最后才写 beats」）",
        '''	        write_reg32(DECODER_BASEADDR, DECODER_REG_OUT_BEATS, DEC_OUT_BEATS);
	        usleep(100);
	        write_reg32(DECODER_BASEADDR, DECODER_REG_IN_BEATS, DEC_IN_BEATS);  // 最后写''',
        '''	        write_reg32(DECODER_BASEADDR, DECODER_REG_IN_BEATS, DEC_IN_BEATS);
	        usleep(100);
	        write_reg32(DECODER_BASEADDR, DECODER_REG_OUT_BEATS, DEC_OUT_BEATS);''',
    ),
    "voter-prestart-zero": (
        "删掉 Voter START 脉冲前那次「先写 0」（脉冲的起点被整理掉）",
        '''        write_reg32(VOTER_BASEADDR, VOTER_REG_START, 0x00);
        usleep(100);

        u32 status_before_start = read_reg32(VOTER_BASEADDR, VOTER_REG_STATUS);''',
        '''        u32 status_before_start = read_reg32(VOTER_BASEADDR, VOTER_REG_STATUS);''',
    ),
    "drop-stage2-invalidate": (
        "删掉 Stage2 输入区的分块 invalidate（「缓存维护是样板代码」这个误解）",
        '''            Xil_DCacheInvalidateRange(VOTER_IN_TEMP + inv_done, chunk);
            inv_done += chunk;''',
        '''            inv_done += chunk;''',
    ),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--what", required=True, choices=sorted(INJECTIONS))
    ap.add_argument("--describe", action="store_true")
    a = ap.parse_args()

    desc, old, new = INJECTIONS[a.what]
    if a.describe:
        print(desc)
        return 0

    src = open(a.src, encoding="utf-8").read()
    n = src.count(old)
    if n != 1:
        sys.stderr.write(
            f"[inject] 注入点 '{a.what}' 在 {a.src} 里出现 {n} 次（应为 1 次）。\n"
            f"         echo.c 变了，请更新 tests/host/inject.py 的注入点，\n"
            f"         不要让鉴别力自证悄悄变成空操作。\n")
        return 2
    open(a.out, "w", encoding="utf-8").write(src.replace(old, new, 1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
