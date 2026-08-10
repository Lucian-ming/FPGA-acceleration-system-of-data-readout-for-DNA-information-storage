// =============================================================
// 5b -> 4b 反稀疏化查找表
//
// ⚠️ 本模块当前未被 desparsification_decoder_v1_0.v 实例化；
//    实际综合进 IP 的是顶层里的 conv40_32() 函数。保留本模块作为
//    可读的规格参考，并已按 docs/02-data-contract.md 校正。
//
// 契约（由 R0.83 黄金数据反解并验证，见 tools/golden_model.py verify-code）：
//   稀疏码本 = 全部汉明重量 <= 2 的 16 个 5-bit 字
//   设一组 5 bit 按【码流顺序】为 b0 b1 b2 b3 b4，
//   则输出 4 bit 按码流顺序为 b1^b0, b2^b0, b3^b0, b4^b0
//   即：第一个 bit 是取反标志，后 4 个 bit 是数据。
//
// 下表的 five_bit_in[4] 对应 b0（组内第一个 bit），
// four_bit_out[3] 对应输出的第一个 bit，与上面的码流顺序一致。
//
// 修订记录：原表有 3 处与契约不符 —— 缺 5'b00100 与 5'b10100，
//          多出汉明重量为 3 的 5'b01011，且 5'b01000 映射错误。
// =============================================================
module five_to_four_decoder(
    input  wire [4:0] five_bit_in,
    output reg  [3:0] four_bit_out
);
    always @(*) begin
        case(five_bit_in)
            // 取反标志为 0：原样透传后 4 bit
            5'b00000: four_bit_out = 4'b0000;
            5'b00001: four_bit_out = 4'b0001;
            5'b00010: four_bit_out = 4'b0010;
            5'b00011: four_bit_out = 4'b0011;
            5'b00100: four_bit_out = 4'b0100;
            5'b00101: four_bit_out = 4'b0101;
            5'b00110: four_bit_out = 4'b0110;
            5'b01000: four_bit_out = 4'b1000;
            5'b01001: four_bit_out = 4'b1001;
            5'b01010: four_bit_out = 4'b1010;
            5'b01100: four_bit_out = 4'b1100;
            // 取反标志为 1：后 4 bit 取反
            5'b10000: four_bit_out = 4'b1111;
            5'b10001: four_bit_out = 4'b1110;
            5'b10010: four_bit_out = 4'b1101;
            5'b10100: four_bit_out = 4'b1011;
            5'b11000: four_bit_out = 4'b0111;
            // 码本外的输入（信道出错时会出现）：按同一规则处理，行为与
            // 顶层 conv40_32() 一致，交由后级 LDPC 纠正。
            default : four_bit_out = five_bit_in[3:0] ^ {4{five_bit_in[4]}};
        endcase
    end
endmodule
