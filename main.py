import tkinter as tk
import sys
from app.gui import OreScanGUI


def main():
    root = tk.Tk()
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass
    app = OreScanGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
