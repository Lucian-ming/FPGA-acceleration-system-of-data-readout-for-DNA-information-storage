# Definitional proc to organize widgets for parameters.
proc init_gui { IPINST } {
  ipgui::add_param $IPINST -name "Component_Name"
  set Stage1 [ipgui::add_page $IPINST -name "Stage1"]
  ipgui::add_param $IPINST -name "C_STAGE1_P_WAYS" -parent $Stage1 -widget comboBox
  ipgui::add_param $IPINST -name "C_STAGE1_PIPE_TREE" -parent $Stage1 -widget comboBox
  #Adding Page
  set Page_0 [ipgui::add_page $IPINST -name "Page 0"]
  ipgui::add_param $IPINST -name "C_S_AXI_LITE_CTRL_DATA_WIDTH" -parent ${Page_0} -widget comboBox
  ipgui::add_param $IPINST -name "C_S_AXI_LITE_CTRL_ADDR_WIDTH" -parent ${Page_0}
  ipgui::add_param $IPINST -name "C_S_AXI_LITE_CTRL_BASEADDR" -parent ${Page_0}
  ipgui::add_param $IPINST -name "C_S_AXI_LITE_CTRL_HIGHADDR" -parent ${Page_0}


}

proc update_PARAM_VALUE.BATCH { PARAM_VALUE.BATCH } {
	# Procedure called to update BATCH when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.BATCH { PARAM_VALUE.BATCH } {
	# Procedure called to validate BATCH
	return true
}

proc update_PARAM_VALUE.CODEBITS { PARAM_VALUE.CODEBITS } {
	# Procedure called to update CODEBITS when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.CODEBITS { PARAM_VALUE.CODEBITS } {
	# Procedure called to validate CODEBITS
	return true
}

proc update_PARAM_VALUE.C_M_AXIS_RESULT_TDATA_WIDTH { PARAM_VALUE.C_M_AXIS_RESULT_TDATA_WIDTH } {
	# Procedure called to update C_M_AXIS_RESULT_TDATA_WIDTH when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.C_M_AXIS_RESULT_TDATA_WIDTH { PARAM_VALUE.C_M_AXIS_RESULT_TDATA_WIDTH } {
	# Procedure called to validate C_M_AXIS_RESULT_TDATA_WIDTH
	return true
}

proc update_PARAM_VALUE.C_S_AXIS_DATA_TDATA_WIDTH { PARAM_VALUE.C_S_AXIS_DATA_TDATA_WIDTH } {
	# Procedure called to update C_S_AXIS_DATA_TDATA_WIDTH when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.C_S_AXIS_DATA_TDATA_WIDTH { PARAM_VALUE.C_S_AXIS_DATA_TDATA_WIDTH } {
	# Procedure called to validate C_S_AXIS_DATA_TDATA_WIDTH
	return true
}

proc update_PARAM_VALUE.NUM_LC { PARAM_VALUE.NUM_LC } {
	# Procedure called to update NUM_LC when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.NUM_LC { PARAM_VALUE.NUM_LC } {
	# Procedure called to validate NUM_LC
	return true
}

proc update_PARAM_VALUE.POS_W { PARAM_VALUE.POS_W } {
	# Procedure called to update POS_W when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.POS_W { PARAM_VALUE.POS_W } {
	# Procedure called to validate POS_W
	return true
}

proc update_PARAM_VALUE.READ_BPS { PARAM_VALUE.READ_BPS } {
	# Procedure called to update READ_BPS when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.READ_BPS { PARAM_VALUE.READ_BPS } {
	# Procedure called to validate READ_BPS
	return true
}

proc update_PARAM_VALUE.REF_LEN { PARAM_VALUE.REF_LEN } {
	# Procedure called to update REF_LEN when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.REF_LEN { PARAM_VALUE.REF_LEN } {
	# Procedure called to validate REF_LEN
	return true
}

proc update_PARAM_VALUE.RESULT_W { PARAM_VALUE.RESULT_W } {
	# Procedure called to update RESULT_W when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.RESULT_W { PARAM_VALUE.RESULT_W } {
	# Procedure called to validate RESULT_W
	return true
}

proc update_PARAM_VALUE.SCORE_W { PARAM_VALUE.SCORE_W } {
	# Procedure called to update SCORE_W when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.SCORE_W { PARAM_VALUE.SCORE_W } {
	# Procedure called to validate SCORE_W
	return true
}

proc update_PARAM_VALUE.STRIDE { PARAM_VALUE.STRIDE } {
	# Procedure called to update STRIDE when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.STRIDE { PARAM_VALUE.STRIDE } {
	# Procedure called to validate STRIDE
	return true
}

proc update_PARAM_VALUE.C_S_AXI_LITE_CTRL_DATA_WIDTH { PARAM_VALUE.C_S_AXI_LITE_CTRL_DATA_WIDTH } {
	# Procedure called to update C_S_AXI_LITE_CTRL_DATA_WIDTH when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.C_S_AXI_LITE_CTRL_DATA_WIDTH { PARAM_VALUE.C_S_AXI_LITE_CTRL_DATA_WIDTH } {
	# Procedure called to validate C_S_AXI_LITE_CTRL_DATA_WIDTH
	return true
}

proc update_PARAM_VALUE.C_S_AXI_LITE_CTRL_ADDR_WIDTH { PARAM_VALUE.C_S_AXI_LITE_CTRL_ADDR_WIDTH } {
	# Procedure called to update C_S_AXI_LITE_CTRL_ADDR_WIDTH when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.C_S_AXI_LITE_CTRL_ADDR_WIDTH { PARAM_VALUE.C_S_AXI_LITE_CTRL_ADDR_WIDTH } {
	# Procedure called to validate C_S_AXI_LITE_CTRL_ADDR_WIDTH
	return true
}

proc update_PARAM_VALUE.C_S_AXI_LITE_CTRL_BASEADDR { PARAM_VALUE.C_S_AXI_LITE_CTRL_BASEADDR } {
	# Procedure called to update C_S_AXI_LITE_CTRL_BASEADDR when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.C_S_AXI_LITE_CTRL_BASEADDR { PARAM_VALUE.C_S_AXI_LITE_CTRL_BASEADDR } {
	# Procedure called to validate C_S_AXI_LITE_CTRL_BASEADDR
	return true
}

proc update_PARAM_VALUE.C_S_AXI_LITE_CTRL_HIGHADDR { PARAM_VALUE.C_S_AXI_LITE_CTRL_HIGHADDR } {
	# Procedure called to update C_S_AXI_LITE_CTRL_HIGHADDR when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.C_S_AXI_LITE_CTRL_HIGHADDR { PARAM_VALUE.C_S_AXI_LITE_CTRL_HIGHADDR } {
	# Procedure called to validate C_S_AXI_LITE_CTRL_HIGHADDR
	return true
}


proc update_MODELPARAM_VALUE.C_S_AXI_LITE_CTRL_DATA_WIDTH { MODELPARAM_VALUE.C_S_AXI_LITE_CTRL_DATA_WIDTH PARAM_VALUE.C_S_AXI_LITE_CTRL_DATA_WIDTH } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.C_S_AXI_LITE_CTRL_DATA_WIDTH}] ${MODELPARAM_VALUE.C_S_AXI_LITE_CTRL_DATA_WIDTH}
}

proc update_MODELPARAM_VALUE.C_S_AXI_LITE_CTRL_ADDR_WIDTH { MODELPARAM_VALUE.C_S_AXI_LITE_CTRL_ADDR_WIDTH PARAM_VALUE.C_S_AXI_LITE_CTRL_ADDR_WIDTH } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.C_S_AXI_LITE_CTRL_ADDR_WIDTH}] ${MODELPARAM_VALUE.C_S_AXI_LITE_CTRL_ADDR_WIDTH}
}

proc update_MODELPARAM_VALUE.C_M_AXIS_RESULT_TDATA_WIDTH { MODELPARAM_VALUE.C_M_AXIS_RESULT_TDATA_WIDTH PARAM_VALUE.C_M_AXIS_RESULT_TDATA_WIDTH } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.C_M_AXIS_RESULT_TDATA_WIDTH}] ${MODELPARAM_VALUE.C_M_AXIS_RESULT_TDATA_WIDTH}
}

proc update_MODELPARAM_VALUE.C_S_AXIS_DATA_TDATA_WIDTH { MODELPARAM_VALUE.C_S_AXIS_DATA_TDATA_WIDTH PARAM_VALUE.C_S_AXIS_DATA_TDATA_WIDTH } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.C_S_AXIS_DATA_TDATA_WIDTH}] ${MODELPARAM_VALUE.C_S_AXIS_DATA_TDATA_WIDTH}
}

proc update_MODELPARAM_VALUE.READ_BPS { MODELPARAM_VALUE.READ_BPS PARAM_VALUE.READ_BPS } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.READ_BPS}] ${MODELPARAM_VALUE.READ_BPS}
}

proc update_MODELPARAM_VALUE.CODEBITS { MODELPARAM_VALUE.CODEBITS PARAM_VALUE.CODEBITS } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.CODEBITS}] ${MODELPARAM_VALUE.CODEBITS}
}

proc update_MODELPARAM_VALUE.SCORE_W { MODELPARAM_VALUE.SCORE_W PARAM_VALUE.SCORE_W } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.SCORE_W}] ${MODELPARAM_VALUE.SCORE_W}
}

proc update_MODELPARAM_VALUE.POS_W { MODELPARAM_VALUE.POS_W PARAM_VALUE.POS_W } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.POS_W}] ${MODELPARAM_VALUE.POS_W}
}

proc update_MODELPARAM_VALUE.RESULT_W { MODELPARAM_VALUE.RESULT_W PARAM_VALUE.RESULT_W } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.RESULT_W}] ${MODELPARAM_VALUE.RESULT_W}
}

proc update_MODELPARAM_VALUE.BATCH { MODELPARAM_VALUE.BATCH PARAM_VALUE.BATCH } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.BATCH}] ${MODELPARAM_VALUE.BATCH}
}

proc update_MODELPARAM_VALUE.NUM_LC { MODELPARAM_VALUE.NUM_LC PARAM_VALUE.NUM_LC } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.NUM_LC}] ${MODELPARAM_VALUE.NUM_LC}
}

proc update_MODELPARAM_VALUE.STRIDE { MODELPARAM_VALUE.STRIDE PARAM_VALUE.STRIDE } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.STRIDE}] ${MODELPARAM_VALUE.STRIDE}
}

proc update_MODELPARAM_VALUE.REF_LEN { MODELPARAM_VALUE.REF_LEN PARAM_VALUE.REF_LEN } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.REF_LEN}] ${MODELPARAM_VALUE.REF_LEN}
}


# 生产配置只有4/0与16/1；不允许16路组合树静默进入100MHz工程。
proc update_PARAM_VALUE.C_STAGE1_P_WAYS { PARAM_VALUE.C_STAGE1_P_WAYS } {}
proc validate_PARAM_VALUE.C_STAGE1_P_WAYS { PARAM_VALUE.C_STAGE1_P_WAYS } {
    set ways [get_property value ${PARAM_VALUE.C_STAGE1_P_WAYS}]
    if {$ways == 4 || $ways == 16} { return true }
    return false
}
proc update_PARAM_VALUE.C_STAGE1_PIPE_TREE { PARAM_VALUE.C_STAGE1_PIPE_TREE } {}
proc validate_PARAM_VALUE.C_STAGE1_PIPE_TREE { PARAM_VALUE.C_STAGE1_PIPE_TREE PARAM_VALUE.C_STAGE1_P_WAYS } {
    set ways [get_property value ${PARAM_VALUE.C_STAGE1_P_WAYS}]
    set pipe [get_property value ${PARAM_VALUE.C_STAGE1_PIPE_TREE}]
    if {($ways == 4 && $pipe == 0) || ($ways == 16 && $pipe == 1)} { return true }
    return false
}
proc update_MODELPARAM_VALUE.C_STAGE1_P_WAYS { MODELPARAM_VALUE.C_STAGE1_P_WAYS PARAM_VALUE.C_STAGE1_P_WAYS } {
    set_property value [get_property value ${PARAM_VALUE.C_STAGE1_P_WAYS}] ${MODELPARAM_VALUE.C_STAGE1_P_WAYS}
}
proc update_MODELPARAM_VALUE.C_STAGE1_PIPE_TREE { MODELPARAM_VALUE.C_STAGE1_PIPE_TREE PARAM_VALUE.C_STAGE1_PIPE_TREE } {
    set_property value [get_property value ${PARAM_VALUE.C_STAGE1_PIPE_TREE}] ${MODELPARAM_VALUE.C_STAGE1_PIPE_TREE}
}
