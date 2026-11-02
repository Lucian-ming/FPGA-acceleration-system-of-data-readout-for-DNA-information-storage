# Definitional proc to organize widgets for parameters.
proc init_gui { IPINST } {
  ipgui::add_param $IPINST -name "Component_Name"
  #Adding Page
  set Page_0 [ipgui::add_page $IPINST -name "Page 0"]
  ipgui::add_param $IPINST -name "C_S00_AXI_DATA_WIDTH" -parent ${Page_0} -widget comboBox
  ipgui::add_param $IPINST -name "C_S00_AXI_ADDR_WIDTH" -parent ${Page_0}
  ipgui::add_param $IPINST -name "C_S00_AXI_BASEADDR" -parent ${Page_0}
  ipgui::add_param $IPINST -name "C_S00_AXI_HIGHADDR" -parent ${Page_0}
  ipgui::add_param $IPINST -name "C_M00_AXI_ADDR_WIDTH" -parent ${Page_0}
  ipgui::add_param $IPINST -name "C_M00_AXI_DATA_WIDTH" -parent ${Page_0} -widget comboBox


}

proc update_PARAM_VALUE.CODEWORD_BITS { PARAM_VALUE.CODEWORD_BITS } {
	# Procedure called to update CODEWORD_BITS when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.CODEWORD_BITS { PARAM_VALUE.CODEWORD_BITS } {
	# Procedure called to validate CODEWORD_BITS
	return true
}

proc update_PARAM_VALUE.FAST_INIT { PARAM_VALUE.FAST_INIT } {
	# Procedure called to update FAST_INIT when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.FAST_INIT { PARAM_VALUE.FAST_INIT } {
	# Procedure called to validate FAST_INIT
	return true
}

proc update_PARAM_VALUE.LAYER_SIZE { PARAM_VALUE.LAYER_SIZE } {
	# Procedure called to update LAYER_SIZE when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.LAYER_SIZE { PARAM_VALUE.LAYER_SIZE } {
	# Procedure called to validate LAYER_SIZE
	return true
}

proc update_PARAM_VALUE.MAX_BURST_LEN { PARAM_VALUE.MAX_BURST_LEN } {
	# Procedure called to update MAX_BURST_LEN when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.MAX_BURST_LEN { PARAM_VALUE.MAX_BURST_LEN } {
	# Procedure called to validate MAX_BURST_LEN
	return true
}

proc update_PARAM_VALUE.TOTAL_BITS { PARAM_VALUE.TOTAL_BITS } {
	# Procedure called to update TOTAL_BITS when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.TOTAL_BITS { PARAM_VALUE.TOTAL_BITS } {
	# Procedure called to validate TOTAL_BITS
	return true
}

proc update_PARAM_VALUE.UPPER_LAYER_BITS { PARAM_VALUE.UPPER_LAYER_BITS } {
	# Procedure called to update UPPER_LAYER_BITS when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.UPPER_LAYER_BITS { PARAM_VALUE.UPPER_LAYER_BITS } {
	# Procedure called to validate UPPER_LAYER_BITS
	return true
}

proc update_PARAM_VALUE.C_S00_AXI_DATA_WIDTH { PARAM_VALUE.C_S00_AXI_DATA_WIDTH } {
	# Procedure called to update C_S00_AXI_DATA_WIDTH when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.C_S00_AXI_DATA_WIDTH { PARAM_VALUE.C_S00_AXI_DATA_WIDTH } {
	# Procedure called to validate C_S00_AXI_DATA_WIDTH
	return true
}

proc update_PARAM_VALUE.C_S00_AXI_ADDR_WIDTH { PARAM_VALUE.C_S00_AXI_ADDR_WIDTH } {
	# Procedure called to update C_S00_AXI_ADDR_WIDTH when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.C_S00_AXI_ADDR_WIDTH { PARAM_VALUE.C_S00_AXI_ADDR_WIDTH } {
	# Procedure called to validate C_S00_AXI_ADDR_WIDTH
	return true
}

proc update_PARAM_VALUE.C_S00_AXI_BASEADDR { PARAM_VALUE.C_S00_AXI_BASEADDR } {
	# Procedure called to update C_S00_AXI_BASEADDR when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.C_S00_AXI_BASEADDR { PARAM_VALUE.C_S00_AXI_BASEADDR } {
	# Procedure called to validate C_S00_AXI_BASEADDR
	return true
}

proc update_PARAM_VALUE.C_S00_AXI_HIGHADDR { PARAM_VALUE.C_S00_AXI_HIGHADDR } {
	# Procedure called to update C_S00_AXI_HIGHADDR when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.C_S00_AXI_HIGHADDR { PARAM_VALUE.C_S00_AXI_HIGHADDR } {
	# Procedure called to validate C_S00_AXI_HIGHADDR
	return true
}

proc update_PARAM_VALUE.C_M00_AXI_ADDR_WIDTH { PARAM_VALUE.C_M00_AXI_ADDR_WIDTH } {
	# Procedure called to update C_M00_AXI_ADDR_WIDTH when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.C_M00_AXI_ADDR_WIDTH { PARAM_VALUE.C_M00_AXI_ADDR_WIDTH } {
	# Procedure called to validate C_M00_AXI_ADDR_WIDTH
	return true
}

proc update_PARAM_VALUE.C_M00_AXI_DATA_WIDTH { PARAM_VALUE.C_M00_AXI_DATA_WIDTH } {
	# Procedure called to update C_M00_AXI_DATA_WIDTH when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.C_M00_AXI_DATA_WIDTH { PARAM_VALUE.C_M00_AXI_DATA_WIDTH } {
	# Procedure called to validate C_M00_AXI_DATA_WIDTH
	return true
}


proc update_MODELPARAM_VALUE.C_S00_AXI_DATA_WIDTH { MODELPARAM_VALUE.C_S00_AXI_DATA_WIDTH PARAM_VALUE.C_S00_AXI_DATA_WIDTH } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.C_S00_AXI_DATA_WIDTH}] ${MODELPARAM_VALUE.C_S00_AXI_DATA_WIDTH}
}

proc update_MODELPARAM_VALUE.C_S00_AXI_ADDR_WIDTH { MODELPARAM_VALUE.C_S00_AXI_ADDR_WIDTH PARAM_VALUE.C_S00_AXI_ADDR_WIDTH } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.C_S00_AXI_ADDR_WIDTH}] ${MODELPARAM_VALUE.C_S00_AXI_ADDR_WIDTH}
}

proc update_MODELPARAM_VALUE.C_M00_AXI_ADDR_WIDTH { MODELPARAM_VALUE.C_M00_AXI_ADDR_WIDTH PARAM_VALUE.C_M00_AXI_ADDR_WIDTH } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.C_M00_AXI_ADDR_WIDTH}] ${MODELPARAM_VALUE.C_M00_AXI_ADDR_WIDTH}
}

proc update_MODELPARAM_VALUE.C_M00_AXI_DATA_WIDTH { MODELPARAM_VALUE.C_M00_AXI_DATA_WIDTH PARAM_VALUE.C_M00_AXI_DATA_WIDTH } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.C_M00_AXI_DATA_WIDTH}] ${MODELPARAM_VALUE.C_M00_AXI_DATA_WIDTH}
}

proc update_MODELPARAM_VALUE.MAX_BURST_LEN { MODELPARAM_VALUE.MAX_BURST_LEN PARAM_VALUE.MAX_BURST_LEN } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.MAX_BURST_LEN}] ${MODELPARAM_VALUE.MAX_BURST_LEN}
}

proc update_MODELPARAM_VALUE.TOTAL_BITS { MODELPARAM_VALUE.TOTAL_BITS PARAM_VALUE.TOTAL_BITS } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.TOTAL_BITS}] ${MODELPARAM_VALUE.TOTAL_BITS}
}

proc update_MODELPARAM_VALUE.CODEWORD_BITS { MODELPARAM_VALUE.CODEWORD_BITS PARAM_VALUE.CODEWORD_BITS } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.CODEWORD_BITS}] ${MODELPARAM_VALUE.CODEWORD_BITS}
}

proc update_MODELPARAM_VALUE.FAST_INIT { MODELPARAM_VALUE.FAST_INIT PARAM_VALUE.FAST_INIT } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.FAST_INIT}] ${MODELPARAM_VALUE.FAST_INIT}
}

proc update_MODELPARAM_VALUE.UPPER_LAYER_BITS { MODELPARAM_VALUE.UPPER_LAYER_BITS PARAM_VALUE.UPPER_LAYER_BITS } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.UPPER_LAYER_BITS}] ${MODELPARAM_VALUE.UPPER_LAYER_BITS}
}

proc update_MODELPARAM_VALUE.LAYER_SIZE { MODELPARAM_VALUE.LAYER_SIZE PARAM_VALUE.LAYER_SIZE } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.LAYER_SIZE}] ${MODELPARAM_VALUE.LAYER_SIZE}
}

