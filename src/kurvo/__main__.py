import os
import sys


def main():
    import pyqtgraph as pg
    from PySide6.QtWidgets import QApplication

    from .vista.ventana import VentanaPrincipal

    from .vista import iconos

    pg.setConfigOptions(antialias=True, background="w", foreground="k")
    if sys.platform == "win32":     # icono propio en la barra de tareas (si no, sale el de Python)
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Kurvo.App")
        except (AttributeError, OSError):
            pass
    app = QApplication(sys.argv)
    app.setApplicationName("Kurvo")
    app.setWindowIcon(iconos.icono("app"))
    ventana = VentanaPrincipal()
    ventana.show()
    if len(sys.argv) > 1:
        ruta = sys.argv[1]
        if ruta.lower().endswith(".las"):
            ventana.importar_las(None, ruta)
        else:
            ventana.abrir(ruta)
    prueba = os.environ.get("KURVO_PRUEBA_ARRANQUE")
    if prueba:      # prueba del ejecutable: guarda una captura y sale (empaquetado/construir.bat, D102)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(2000, lambda: (ventana.grab().save(prueba), ventana.proyecto.__setattr__("modificado", False),
                                         app.quit()))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
