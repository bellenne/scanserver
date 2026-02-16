from __future__ import annotations

from typing import Any


def show_defect_window(
    payload: str,
    user_name: str,
    device_id: str,
) -> dict[str, Any] | None:
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title(f"DEFECT | {device_id}")
    root.geometry("560x380")
    root.resizable(False, False)

    result: dict[str, Any] | None = None

    frm = ttk.Frame(root, padding=12)
    frm.pack(fill="both", expand=True)

    # payload (readonly)
    ttk.Label(frm, text="QR / Payload:", font=("Segoe UI", 9, "bold")).pack(anchor="w")
    txt = tk.Text(frm, height=4, wrap="word")
    txt.insert("1.0", payload)
    txt.configure(state="disabled")
    txt.pack(fill="x", pady=(4, 10))

    # user name (readonly)
    ttk.Label(frm, text=f"Пользователь: {user_name}", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 10))

    # product type
    ttk.Label(frm, text="Тип изделия:", font=("Segoe UI", 9, "bold")).pack(anchor="w")
    prod_var = tk.StringVar(value="wallpaper")  # default
    prod_row = ttk.Frame(frm)
    prod_row.pack(fill="x", pady=(4, 10))
    ttk.Radiobutton(prod_row, text="Обои", value="wallpaper", variable=prod_var).pack(side="left", padx=(0, 12))
    ttk.Radiobutton(prod_row, text="Футболки", value="tshirt", variable=prod_var).pack(side="left")

    # numbers/qty
    ttk.Label(
        frm,
        text="Для футболок укажите общее количество, для обоев укажите номера полотен через запятую 1,2,3",
        font=("Segoe UI", 9, "bold"),
        wraplength=520,
        justify="left",
    ).pack(anchor="w")
    numbers_var = tk.StringVar(value="")
    numbers_entry = ttk.Entry(frm, textvariable=numbers_var)
    numbers_entry.pack(fill="x", pady=(4, 10))
    numbers_entry.focus_set()

    # comment
    ttk.Label(frm, text="Комментарий:", font=("Segoe UI", 9, "bold")).pack(anchor="w")
    comment_var = tk.StringVar(value="")
    comment_entry = ttk.Entry(frm, textvariable=comment_var)
    comment_entry.pack(fill="x", pady=(4, 10))

    # buttons
    btns = ttk.Frame(frm)
    btns.pack(fill="x", pady=(10, 0))

    error_var = tk.StringVar(value="")
    error_label = ttk.Label(frm, textvariable=error_var, foreground="red")
    error_label.pack(anchor="w", pady=(4, 0))

    def _validate() -> bool:
        numbers = numbers_var.get().strip()
        comment = comment_var.get().strip()

        if not numbers:
            error_var.set("Заполните номера полотен или количество.")
            return False

        if not comment:
            error_var.set("Комментарий обязателен для заполнения.")
            return False

        error_var.set("")
        return True

    def on_send() -> None:
        nonlocal result
        if not _validate():
            return

        result = {
            "submit": "send",
            "product_type": prod_var.get().strip(),
            "numbers": numbers_var.get().strip(),
            "comment": comment_var.get().strip(),
        }
        root.destroy()

    def on_cancel() -> None:
        nonlocal result
        result = None
        root.destroy()

    ttk.Button(btns, text="Отменить", command=on_cancel).pack(side="right")
    ttk.Button(btns, text="Отправить", command=on_send).pack(side="right", padx=(0, 8))

    root.mainloop()
    return result
