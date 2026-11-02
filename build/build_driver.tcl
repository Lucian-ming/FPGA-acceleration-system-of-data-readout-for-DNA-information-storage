# Windows 构建驱动：从 build.config 读取 key=value，设置 ::argv 后调用 build.tcl。
# 目的：绕开 cmd 批处理把 "key=value" 按 '=' 拆成两个参数的问题。
# Windows 版 Vivado 默认按系统代码页读 Tcl；必须先切 UTF-8，否则中文注释/字符串会被读乱。
encoding system utf-8

set _here [file normalize [file dirname [info script]]]
set _root [file normalize [file join $_here ..]]
set _cfg  [file join $_here build.config]
if {![file isfile $_cfg]} { error "缺少 build.config: $_cfg" }
set _fh [open $_cfg r]; set _txt [read $_fh]; close $_fh
set ::argv {}
foreach _line [split $_txt "\n"] {
  set _line [string trim $_line]
  if {$_line eq "" || [string index $_line 0] eq "#"} continue
  lappend ::argv $_line
}
puts "===> build.config argv: $::argv"
source [file join $_root src hw scripts build.tcl]
