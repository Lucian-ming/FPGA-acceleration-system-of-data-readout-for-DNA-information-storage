# 显式板卡注册表；未知/未验证配置必须在 create_project 之前失败。
proc dna_load_board {repo_root board_id} {
  if {![regexp {^[a-z][a-z0-9_]*$} $board_id]} {
    error "非法 board 标识：$board_id"
  }
  set config_path [file join $repo_root hw boards ${board_id}.tcl]
  if {![file isfile $config_path] || $board_id eq "load_board"} {
    error "未知板配置 '$board_id'；禁止静默回退到其他板配置"
  }
  source $config_path
  foreach key {id ready part} {
    if {![info exists board_config] || ![dict exists $board_config $key]} {
      error "板配置 $config_path 缺少字段 $key"
    }
  }
  if {[dict get $board_config id] ne $board_id} {error "board id 与配置文件不一致"}
  if {[dict get $board_config ready] ne "1"} {
    error "板配置 '$board_id' 尚未验证：[dict get $board_config pending]"
  }
  foreach key {uart xdc source_refs ps7_properties} {
    if {![dict exists $board_config $key] || [dict get $board_config $key] eq ""} {
      error "已启用板配置 $board_id 缺少有效字段 $key"
    }
  }
  dict set board_config config_path [file normalize $config_path]
  return $board_config
}
