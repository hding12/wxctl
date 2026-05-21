#!/usr/bin/env python3
"""Vendored LLDB-based client key capture.

Adapted from an upstream LLDB capture script under the WTFPL license. This copy is intentionally self-contained so wxctl
does not depend on the upstream repository at runtime.
"""

from __future__ import annotations

import glob
import json
import os
from pathlib import Path
import lldb


DB_DIR = os.path.expanduser(
    os.environ.get(
        "WXCTL_XWECHAT_ROOT",
        "~/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files",
    )
)
OUTPUT_FILE = os.path.expanduser(
    os.environ.get("WXCTL_KEY_FILE", "~/Library/Application Support/wxctl/state/wechat_keys.json")
)
PAGE_SZ = 4096
SALT_SZ = 16


def find_db_dir() -> str | None:
    pattern = os.path.join(DB_DIR, "*", "db_storage")
    candidates = glob.glob(pattern)
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        print(f"[*] Found multiple db_storage dirs, using first: {candidates[0]}")
        return candidates[0]
    if os.path.isdir(DB_DIR) and os.path.basename(DB_DIR) == "db_storage":
        return DB_DIR
    return None


def build_salt_to_db_map(db_dir: str) -> dict[str, list[str]]:
    salt_to_dbs: dict[str, list[str]] = {}
    for root, _, files in os.walk(db_dir):
        for filename in files:
            if not filename.endswith(".db") or filename.endswith(("-wal", "-shm")):
                continue
            path = os.path.join(root, filename)
            if os.path.getsize(path) < PAGE_SZ:
                continue
            rel = os.path.relpath(path, db_dir)
            with open(path, "rb") as fh:
                salt = fh.read(PAGE_SZ)[:SALT_SZ].hex()
            salt_to_dbs.setdefault(salt, []).append(rel)
    return salt_to_dbs


def wait_for_stop(process, listener) -> bool:
    event = lldb.SBEvent()
    while True:
        if listener.WaitForEvent(1, event):
            state = lldb.SBProcess.GetStateFromEvent(event)
            if state == lldb.eStateStopped:
                return True
            if state in (lldb.eStateExited, lldb.eStateCrashed, lldb.eStateDetached):
                print(f"[-] Process ended unexpectedly (state={state}).")
                return False


def find_wechat_key() -> None:
    debugger = lldb.SBDebugger.Create()
    debugger.SetAsync(False)
    target = debugger.CreateTarget("")
    error = lldb.SBError()

    print("[*] Attaching to WeChat...")
    process = target.AttachToProcessWithName(debugger.GetListener(), "WeChat", False, error)
    if not error.Success():
        print(f"[-] Error attaching to WeChat: {error.GetCString()}")
        print("[!] Make sure WeChat is running and SIP is disabled during first capture.")
        return

    print(f"[+] Attached to WeChat (PID: {process.GetProcessID()})")
    target = debugger.GetSelectedTarget()

    wechat_module = next(
        (module for module in target.module_iter() if module.GetFileSpec().GetFilename() == "WeChat"),
        None,
    )
    if wechat_module is None:
        print("[-] WeChat module not found.")
        process.Detach()
        return

    text_addr = 0
    text_size = 0
    for i in range(wechat_module.GetNumSections()):
        sec = wechat_module.GetSectionAtIndex(i)
        if sec.GetName() != "__TEXT":
            continue
        for j in range(sec.GetNumSubSections()):
            subsec = sec.GetSubSectionAtIndex(j)
            if subsec.GetName() == "__text":
                text_addr = subsec.GetLoadAddress(target)
                text_size = subsec.GetByteSize()
                break
        break

    if not text_addr:
        print("[-] Could not find __TEXT,__text section.")
        process.Detach()
        return
    print(f"[*] WeChat __TEXT,__text: {hex(text_addr)} - {hex(text_addr + text_size)}")

    malloc_syms = target.FindSymbols("malloc")
    malloc_addr = None
    for sym_ctx in malloc_syms:
        sym = sym_ctx.GetSymbol()
        if sym.IsValid():
            malloc_addr = sym.GetStartAddress().GetLoadAddress(target)
            break
    if not malloc_addr:
        print("[-] Could not resolve malloc address.")
        process.Detach()
        return
    print(f"[*] malloc at {hex(malloc_addr)}")

    candidates: list[tuple[int, str]] = []
    for pattern_name, pattern_int in [("mov w0, #0x43", 0x52800860), ("mov x0, #0x43", 0xD2800860)]:
        search_start = text_addr
        search_end = text_addr + text_size
        while search_start < search_end:
            res = lldb.SBCommandReturnObject()
            command = f"memory find -e (uint32_t){hex(pattern_int)} -- {hex(search_start)} {hex(search_end)}"
            debugger.GetCommandInterpreter().HandleCommand(command, res)
            if not res.Succeeded() or "data found" not in res.GetOutput():
                break
            found = False
            for line in res.GetOutput().strip().split("\n"):
                if "0x" not in line or "data found" in line:
                    continue
                addr = int(line.strip().split("0x")[-1].split()[0].rstrip(":"), 16)
                candidates.append((addr, pattern_name))
                search_start = addr + 4
                found = True
                break
            if not found:
                break

    print(f"[*] Found {len(candidates)} mov x0/w0, #0x43 instructions")

    set_cipher_key_addr = None
    function_name = None
    for addr, pattern_name in candidates:
        has_bl_malloc = False
        for offset in range(4, 20, 4):
            instr_addr = addr + offset
            instr_bytes = process.ReadMemory(instr_addr, 4, error)
            if not error.Success():
                continue
            instr = int.from_bytes(instr_bytes, "little")
            if (instr >> 26) != 0b100101:
                continue
            imm26 = instr & 0x03FFFFFF
            if imm26 & 0x02000000:
                imm26 |= ~0x03FFFFFF
                imm26 &= 0xFFFFFFFFFFFFFFFF
            bl_target = (instr_addr + (imm26 << 2)) & 0xFFFFFFFFFFFFFFFF
            if bl_target == malloc_addr:
                has_bl_malloc = True
                break
            bl_sym = target.ResolveLoadAddress(bl_target).GetSymbol()
            if bl_sym.IsValid() and bl_sym.GetName() == "malloc":
                has_bl_malloc = True
                break
        if not has_bl_malloc:
            continue
        print(f"[+] Found {pattern_name} at {hex(addr)} + bl malloc")
        sb_addr = target.ResolveLoadAddress(addr)
        sym = sb_addr.GetSymbol()
        if sym.IsValid():
            set_cipher_key_addr = sym.GetStartAddress().GetLoadAddress(target)
            function_name = sym.GetName()
            print(f"[+] -> In function {function_name} at {hex(set_cipher_key_addr)}")
        else:
            set_cipher_key_addr = addr
            function_name = f"unknown@{hex(addr)}"
        break

    if set_cipher_key_addr is None:
        print("[-] Could not find setCipherKey function.")
        process.Detach()
        return

    print(f"[+] setCipherKey function: {hex(set_cipher_key_addr)} ({function_name})")
    target.BreakpointCreateByAddress(set_cipher_key_addr)
    print(f"[+] Set breakpoint at {hex(set_cipher_key_addr)}")

    listener = debugger.GetListener()
    db_dir = find_db_dir()
    salt_to_dbs: dict[str, list[str]] = {}
    if db_dir:
        print(f"[*] Scanning db files in: {db_dir}")
        salt_to_dbs = build_salt_to_db_map(db_dir)
        print(f"[*] Found {len(salt_to_dbs)} unique salts across db files")
    else:
        print(f"[!] Could not find db_storage directory under {DB_DIR}")

    result: dict[str, str] = {}
    seen_salts: set[str] = set()
    output_path = Path(OUTPUT_FILE)
    if output_path.is_file():
        try:
            result = json.loads(output_path.read_text(encoding="utf-8"))
            seen_salts = set(result.get("__salts__", []))
            print(f"[*] Loaded {len(result) - (1 if '__salts__' in result else 0)} existing entries from {output_path}")
        except Exception:
            pass

    def save_keys() -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output = dict(result)
        output["__salts__"] = sorted(seen_salts)
        output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[*] Saved {len(output) - 1} keys to {output_path}")

    def parse_and_store_key(raw_key_str: str) -> None:
        inner = raw_key_str[2:-1]
        if len(inner) != 96:
            print(f"[!] Unexpected key length {len(inner)}: {raw_key_str}")
            return
        key = inner[:64]
        salt = inner[64:]
        if salt in seen_salts:
            return
        seen_salts.add(salt)
        db_paths = salt_to_dbs.get(salt, [])
        if not db_paths and db_dir:
            print(f"[*] Unknown salt {salt}, rescanning db files...")
            salt_to_dbs.update(build_salt_to_db_map(db_dir))
            db_paths = salt_to_dbs.get(salt, [])
        if db_paths:
            for db_path in db_paths:
                result[db_path] = key
            print(f"\n[!] Found new key!  salt={salt}  key={key}")
            print(f"    Matched db files: {db_paths}")
        else:
            result[f"unknown_salt_{salt}"] = key
            print(f"\n[!] Found new key!  salt={salt}  key={key}")
            print("    No matching db file found for this salt")
        save_keys()

    debugger.SetAsync(True)
    print("[*] Continuing to collect keys. Press Ctrl+C to stop.")
    try:
        while True:
            process.Continue()
            if not wait_for_stop(process, listener):
                break
            thread = next(
                (
                    process.GetThreadAtIndex(i)
                    for i in range(process.GetNumThreads())
                    if process.GetThreadAtIndex(i).GetStopReason() == lldb.eStopReasonBreakpoint
                ),
                None,
            )
            if thread is None:
                continue
            frame = thread.GetFrameAtIndex(0)
            x1 = frame.FindRegister("x1").GetValueAsUnsigned()
            ptr = process.ReadPointerFromMemory(x1 + 8, error)
            if not error.Success() or ptr == 0:
                continue
            data = process.ReadCStringFromMemory(ptr, 128, error)
            if not error.Success():
                continue
            end_idx = data.find("'", 2)
            if end_idx == -1:
                continue
            key_str = data[: end_idx + 1]
            if key_str.startswith("x'"):
                parse_and_store_key(key_str)
    except KeyboardInterrupt:
        print("\n[*] Stopped by user.")
    finally:
        if seen_salts:
            save_keys()
        process.Detach()
        print("[*] Detached from WeChat.")


if __name__ == "__main__":
    find_wechat_key()
