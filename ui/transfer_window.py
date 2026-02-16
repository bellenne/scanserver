from __future__ import annotations

from typing import Any


SIZES = ["XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL"]


def show_transfer_window(
    *,
    title: str,
    payload: str,
    user_name: str,
    device_id: str,
    with_comment: bool = False,
) -> dict[str, Any] | None:
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title(f"{title} | {device_id}")
    root.geometry("560x460" if with_comment else "560x420")
    root.resizable(False, False)

    result: dict[str, Any] | None = None

    frm = ttk.Frame(root, padding=12)
    frm.pack(fill="both", expand=True)

    ttk.Label(frm, text="QR / Payload:", font=("Segoe UI", 9, "bold")).pack(anchor="w")
    txt = tk.Text(frm, height=4, wrap="word")
    txt.insert("1.0", payload)
    txt.configure(state="disabled")
    txt.pack(fill="x", pady=(4, 10))

    ttk.Label(
        frm,
        text=f"Пользователь: {user_name}",
        font=("Segoe UI", 10, "bold"),
    ).pack(anchor="w", pady=(0, 10))

    ttk.Label(frm, text="Укажите количество по размерам:", font=("Segoe UI", 9, "bold")).pack(anchor="w")

    grid = ttk.Frame(frm)
    grid.pack(fill="x", pady=(8, 10))

    vars_map: dict[str, tk.StringVar] = {}
    entries: list[ttk.Entry] = []

    left = SIZES[:5]
    right = SIZES[5:]

    def add_col(sizes: list[str], col: int) -> None:
        for row, size in enumerate(sizes):
            ttk.Label(grid, text=size).grid(row=row, column=col * 2, sticky="w", padx=(0, 8), pady=4)
            v = tk.StringVar(value="")
            vars_map[size] = v
            e = ttk.Entry(grid, textvariable=v, width=10)
            e.grid(row=row, column=col * 2 + 1, sticky="w", pady=4)
            entries.append(e)

    add_col(left, 0)
    add_col(right, 1)

    if entries:
        entries[0].focus_set()

    comment_var = None
    if with_comment:
        ttk.Label(frm, text="Комментарий:", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        comment_var = tk.StringVar(value="")
        ttk.Entry(frm, textvariable=comment_var).pack(fill="x", pady=(4, 10))

    btns = ttk.Frame(frm)
    btns.pack(fill="x", pady=(10, 0))

    error_var = tk.StringVar(value="")
    ttk.Label(frm, textvariable=error_var, foreground="red").pack(anchor="w", pady=(6, 0))

    def build_done_map() -> dict[str, int] | None:
        out: dict[str, int] = {}
        for size, v in vars_map.items():
            s = v.get().strip()
            if not s:
                continue
            try:
                n = int(s)
            except Exception:
                return None
            if n < 0:
                return None
            if n > 0:
                out[size] = n
        return out if out else None

    def _validate(dm: dict[str, int] | None) -> bool:
        if dm is None:
            error_var.set("Заполните хотя бы один размер (число).")
            return False

        if with_comment:
            if comment_var is None or not comment_var.get().strip():
                error_var.set("Комментарий обязателен для заполнения.")
                return False

        error_var.set("")
        return True

    def on_send() -> None:
        nonlocal result
        dm = build_done_map()
        if not _validate(dm):
            return

        result = {
            "done_map": dm,
            "comment": comment_var.get().strip() if comment_var else "",
        }
        root.destroy()

    def on_cancel() -> None:
        nonlocal result
        result = None
        root.destroy()

    ttk.Button(btns, text="Отмена", command=on_cancel).pack(side="right")
    ttk.Button(btns, text="Отправить", command=on_send).pack(side="right", padx=(0, 8))

    root.mainloop()
    return result
