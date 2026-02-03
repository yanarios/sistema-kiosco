from django import forms

class ImportarProductosForm(forms.Form):
    archivo_excel = forms.FileField(
        label="Seleccionar archivo Excel o CSV",
        help_text="Columnas requeridas: codigo, nombre, venta. Opcionales: costo, stock, categoria."
    )