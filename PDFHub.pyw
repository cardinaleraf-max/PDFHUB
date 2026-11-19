try:
    from desktop import main
    main()
except Exception as error:
    import ctypes
    ctypes.windll.user32.MessageBoxW(0, str(error), "PDFHub", 0x10)
