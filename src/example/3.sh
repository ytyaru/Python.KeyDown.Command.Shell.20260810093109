#!/usr/bin/env bash
set -Ceu
#---------------------------------------------------------------------------
# kd動作確認
#---------------------------------------------------------------------------
Run() {
	THIS="$(realpath "${BASH_SOURCE:-0}")"; HERE="$(dirname "$THIS")"; PARENT="$(dirname "$HERE")"; THIS_NAME="$(basename "$THIS")"; APP_ROOT="$PARENT";
	cd "$HERE"
	local langs='Python JavaScript Java C C++ C# TypeScript PHP Ruby Go Swift Kotlin Rust OCaml Haskell Scala Dart Zig Lua Perl Bash PowerShell Ruby Basic VBA AutoHotkey AppleScript EmacsLisp TeX SQL HTML XML XHTML YAML JSON TOML Markdown AsciiDoc OrgMode CSS SCSS SASS Less Stylus PostCSS SVG Graphviz GLSL WGSL MATLAB R Solidity VHDL Verilog RegularExpression'
	local selected=$(../kd.py $langs)
	echo "選択値: ${selected}"
}
Run "$@"
