module five_to_four_decoder(
    input  wire [4:0] five_bit_in,
    output reg  [3:0] four_bit_out
);
    always @(*) begin
        case(five_bit_in)
            5'b00000: four_bit_out = 4'b0000;
            5'b00001: four_bit_out = 4'b0001;
            5'b00010: four_bit_out = 4'b0010;
            5'b00011: four_bit_out = 4'b0011;
            5'b01000: four_bit_out = 4'b0100;
            5'b00101: four_bit_out = 4'b0101;
            5'b00110: four_bit_out = 4'b0110;
            5'b11000: four_bit_out = 4'b0111;
            5'b01001: four_bit_out = 4'b1001;
            5'b01010: four_bit_out = 4'b1010;
            5'b01011: four_bit_out = 4'b1011;
            5'b01100: four_bit_out = 4'b1100;
            5'b10010: four_bit_out = 4'b1101;
            5'b10001: four_bit_out = 4'b1110;
            5'b10000: four_bit_out = 4'b1111;
            default : four_bit_out = 4'b0000;
        endcase
    end
endmodule
