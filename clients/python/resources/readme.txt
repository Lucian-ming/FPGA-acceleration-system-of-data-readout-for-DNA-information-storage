【译码依赖文件】
dvb_s2_r5_6.pchk -- 校验矩阵文件
permutation64800 -- 交织顺序文件

【输入】
dec_input.txt    -- 比特合并结果（共64800比特）。

H -- 硬判决标志

【运行方式】
./R5_6_LDPC_hard_decoder.exe  dec_input.txt  TestBitStream.txt image.jpg H


【输出】
TestBitStream.txt -- 译码输出的二进制比特序列
image.jpg -- 重建的图像