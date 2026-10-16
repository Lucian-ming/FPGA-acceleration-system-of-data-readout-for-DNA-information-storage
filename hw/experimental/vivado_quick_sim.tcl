# ========================================================
# Vivado Quick Simulation Script for DNA Accelerator
# Usage: vivado -mode batch -source hw/experimental/vivado_quick_sim.tcl ?-tclargs part_name=<device>?
# Or in Vivado GUI: Tools -> Run Tcl Script
# ========================================================

puts "========================================"
puts "  DNA Accelerator Quick Simulation"
puts "========================================"

# Project settings
set project_name "dna_sim"
set _script_dir [file normalize [file dirname [info script]]]
set repo_root [file normalize [file join $_script_dir ../..]]
source [file join $repo_root hw boards load_board.tcl]
set board_config [dna_load_board $repo_root bkb220]
set part_name [dict get $board_config part]
if {[info exists argv]} {
    if {[llength $argv] > 1} {
        error "用法：-tclargs part_name=<器件>"
    }
    if {[llength $argv] == 1} {
        set arg [lindex $argv 0]
        if {![regexp {^part_name=(.+)$} $arg -> explicit_part]} {
            error "未知参数 '$arg'；支持 part_name=<器件>"
        }
        set part_name $explicit_part
    }
}
set sim_time "100us"

# Create project directory
set project_dir "./vivado_sim_project"
file mkdir $project_dir

puts "\n\[INFO\] Creating simulation project..."
create_project -force $project_name $project_dir -part $part_name

# Add design files
puts "\n\[INFO\] Adding design files..."

# Check required files
set required_files {
    "Dna_accelerator_core_v1_0.v"
    "Dna_accelerator_core_v1_0_S_AXI_LITE_CTRL.v"
    "s2mm_pack64.v"
    "fifo_sync_sdpram_b64.v"
}

set missing_files {}
foreach file $required_files {
    if {![file exists $file]} {
        lappend missing_files $file
        puts "  \[WARNING\] Missing file: $file"
    } else {
        puts "  \[OK\] Found file: $file"
    }
}

if {[llength $missing_files] > 0} {
    puts "\n\[ERROR\] Missing required files:"
    foreach file $missing_files {
        puts "  - $file"
    }
    puts "\nPlease copy these files to current directory and run again"
    close_project
    return
}

# Add source files
add_files -norecurse $required_files
set_property file_type Verilog [get_files *.v]

# Add testbench
puts "\n\[INFO\] Adding testbench..."
if {[file exists "tb_dna_quick.v"]} {
    add_files -fileset sim_1 -norecurse tb_dna_quick.v
    set_property top tb_dna_quick [get_filesets sim_1]
} elseif {[file exists "tb_dna_accelerator.v"]} {
    add_files -fileset sim_1 -norecurse tb_dna_accelerator.v
    set_property top tb_dna_accelerator [get_filesets sim_1]
} else {
    puts "\[ERROR\] No testbench file found"
    close_project
    return
}

# Update compile order
update_compile_order -fileset sources_1
update_compile_order -fileset sim_1

# Configure simulation
puts "\n\[INFO\] Configuring simulation options..."
set_property -name {xsim.simulate.runtime} -value $sim_time -objects [get_filesets sim_1]
set_property -name {xsim.simulate.log_all_signals} -value {true} -objects [get_filesets sim_1]

# Launch simulation
puts "\n\[INFO\] Launching simulation (this may take a few minutes)..."
launch_simulation

# Add waveforms
puts "\n\[INFO\] Adding signals to waveform window..."
add_wave {{/tb_dna_quick/clk}}
add_wave {{/tb_dna_quick/rst_n}}
add_wave -divider "Control Signals"
add_wave {{/tb_dna_quick/start}}
add_wave {{/tb_dna_quick/preload}}
add_wave -divider "Input AXIS"
add_wave -radix hexadecimal {{/tb_dna_quick/s_axis_tdata}}
add_wave {{/tb_dna_quick/s_axis_tvalid}}
add_wave {{/tb_dna_quick/s_axis_tready}}
add_wave {{/tb_dna_quick/s_axis_tlast}}
add_wave -divider "Output AXIS"
add_wave -radix hexadecimal {{/tb_dna_quick/m_axis_tdata}}
add_wave {{/tb_dna_quick/m_axis_tvalid}}
add_wave {{/tb_dna_quick/m_axis_tready}}
add_wave {{/tb_dna_quick/m_axis_tlast}}
add_wave -divider "Internal Status"
add_wave {{/tb_dna_quick/dut/eng_busy}}
add_wave {{/tb_dna_quick/dut/eng_done}}
add_wave -radix unsigned {{/tb_dna_quick/dut/in_count}}
add_wave -divider "Test Progress"
add_wave -radix unsigned {{/tb_dna_quick/send_count}}
add_wave -radix unsigned {{/tb_dna_quick/recv_count}}

# Run simulation
puts "\n\[INFO\] Running simulation for $sim_time ..."
run $sim_time

# Zoom to fit
zoom full

# Save waveform configuration
puts "\n\[INFO\] Saving waveform configuration..."
save_wave_config dna_sim.wcfg

puts "\n========================================"
puts "  Simulation Complete!"
puts "========================================"
puts "\nResults:"
puts "  - Waveform loaded in Vivado GUI"
puts "  - Check Console window for logs"
puts "  - Waveform config saved to: dna_sim.wcfg"
puts "\nHow to check results:"
puts "  1. Check signals in waveform window"
puts "  2. Check Tcl Console for output logs"
puts "  3. Verify send_count and recv_count match"
puts "\nKey signals:"
puts "  - eng_busy=1   : Engine is working"
puts "  - recv_count   : Number of results received"
puts "  - in_count     : Data count in input FIFO"
puts ""
puts "To re-run: restart; run $sim_time"
puts "To close: close_sim"
puts "========================================"
