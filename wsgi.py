from app import create_app

# Instanciamos la aplicación usando nuestra fábrica
app = create_app()

if __name__ == '__main__':
    # host='0.0.0.0' permite recibir peticiones de otros dispositivos en tu red local
    # (ideal si quieres probar desde tu celular o tablet)
    app.run(host='0.0.0.0', port=5000, debug=True)