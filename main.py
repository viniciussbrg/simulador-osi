import tkinter as tk
from tkinter import messagebox
from simulador.motor import MotorSimulacao
from simulador.visual import InterfaceSimulador

if __name__ == "__main__":
    try:
        motor = MotorSimulacao()
        app = InterfaceSimulador(motor)
        app.root.mainloop()
    except Exception as erro:
        janela = tk.Tk()
        janela.withdraw()
        messagebox.showerror("Simulador OSI", f"Não foi possível iniciar o simulador:\n\n{erro}\n\nVerifique o arquivo topologia.json ao lado do programa.")
