# LDPC IP 参数页：BD 构建脚本会把两个 ROM 文件设为当前 checkout 的绝对路径。
proc init_gui { IPINST } {
  ipgui::add_param $IPINST -name "Component_Name"
  set page [ipgui::add_page $IPINST -name "LDPC ROM"]
  ipgui::add_param $IPINST -name "BT_ROM_FILE" -parent $page
  ipgui::add_param $IPINST -name "BT_OFF_FILE" -parent $page
}

proc validate_PARAM_VALUE.BT_ROM_FILE { PARAM_VALUE.BT_ROM_FILE } {
  return true
}

proc validate_PARAM_VALUE.BT_OFF_FILE { PARAM_VALUE.BT_OFF_FILE } {
  return true
}

proc update_MODELPARAM_VALUE.BT_ROM_FILE { MODELPARAM_VALUE.BT_ROM_FILE PARAM_VALUE.BT_ROM_FILE } {
  set_property value [get_property value ${PARAM_VALUE.BT_ROM_FILE}] ${MODELPARAM_VALUE.BT_ROM_FILE}
}

proc update_MODELPARAM_VALUE.BT_OFF_FILE { MODELPARAM_VALUE.BT_OFF_FILE PARAM_VALUE.BT_OFF_FILE } {
  set_property value [get_property value ${PARAM_VALUE.BT_OFF_FILE}] ${MODELPARAM_VALUE.BT_OFF_FILE}
}
