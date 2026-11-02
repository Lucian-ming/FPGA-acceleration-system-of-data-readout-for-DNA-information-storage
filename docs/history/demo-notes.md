DNA 读出加速系统 —— 演示录制用
================================

gui_app.exe   上位机客户端（2026-11-02 由提交包 src/clients/python 源码打包）
demo-data/    3 组演示用例，均已于 2026-11-02 在 BKB220 板上实测通过
              （板端 syndrome 0/10800，载荷 SHA-256 精确命中，score_min=67）

  用例                       载荷                  板端结果耗时
  06_sailboat_baseline       JPEG 图像 6,746 B     0.90 s
  04_jellybeans_challenge    JPEG 图像 6,725 B     0.88 s   （challenge：误差更高的读段）
  19_utf8_text_baseline      UTF-8 文本 3,300 B    —        （展示非图像载荷）

录制步骤
--------
1. 板卡上电并烧录好 build/artifact 制品；PC 网口 192.168.1.100/24，板端 192.168.1.10:7。
2. 打开 gui_app.exe，读段选 demo-data\<用例>\read.fastq，水印选同目录 watermark.txt。
3. score_min 保持 auto（SE150 自动取 67），点击运行。
4. 完成后界面显示「板端已纠对」，图像类直接显示还原图；可与同目录 reference.jpg 对比，
   expected.txt 里是期望 SHA-256。

不要用 01_peppers：它在板上以 score_min=67 运行时是 SAFE_NOCONV（安全不收敛，不输出载荷），
不适合当成功演示；如需展示「失败时不误判」，可用 02_mandrill_challenge。
