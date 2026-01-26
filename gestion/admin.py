from django.contrib import admin
from .models import Categoria, Producto, SesionCaja, Venta, DetalleVenta, MovimientoCaja
from django.utils.html import format_html 


# Configuración para ver los productos dentro de la Venta
class DetalleVentaInline(admin.TabularInline):
    model = DetalleVenta
    extra = 0  # No mostrar filas vacías extra
    readonly_fields = ('subtotal',) # Que se calcule solo

class VentaAdmin(admin.ModelAdmin):
    inlines = [DetalleVentaInline]
    list_display = ('id', 'fecha', 'metodo_pago', 'total', 'sesion')
    list_filter = ('fecha', 'metodo_pago')
    search_fields = ('id',)

# gestion/admin.py

class ProductoAdmin(admin.ModelAdmin):
    # Usamos 'precio_costo' que es el nombre real en tu modelo
    list_display = ('nombre', 'codigo', 'precio_costo', 'precio_venta', 'stock_actual', 'mostrar_estado', 'activo')
    
    # Acá también: 'precio_costo'
    list_editable = ('stock_actual', 'precio_costo', 'precio_venta') 
    
    search_fields = ('nombre', 'codigo')
    list_filter = ('categoria', 'activo')

    # Semáforo de Stock
    def mostrar_estado(self, obj):
        # Usamos tu campo stock_minimo en lugar de un 5 fijo (más inteligente)
        if obj.stock_actual == 0:
            color = "red"
            texto = "⛔ AGOTADO"
        elif obj.stock_actual <= obj.stock_minimo:
            color = "orange"
            texto = "⚠️ BAJO"
        else:
            color = "green"
            texto = "✅ OK"

        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            texto
        )
    mostrar_estado.short_description = "Estado Stock"

class SesionCajaAdmin(admin.ModelAdmin):
    list_display = ('id', 'usuario', 'fecha_apertura', 'fecha_cierre', 'mostrar_saldo_esperado', 'mostrar_saldo_real', 'mostrar_diferencia', 'estado')
    list_filter = ('fecha_apertura', 'usuario')
    
    # 1. Función para mostrar Saldo Esperado (Si es None muestra -)
    def mostrar_saldo_esperado(self, obj):
        if obj.saldo_final_esperado is not None:
            return f"${obj.saldo_final_esperado}"
        return "-"
    mostrar_saldo_esperado.short_description = "Esperado"

    # 2. Función para mostrar Saldo Real
    def mostrar_saldo_real(self, obj):
        if obj.saldo_final_real is not None:
            return f"${obj.saldo_final_real}"
        return "-"
    mostrar_saldo_real.short_description = "Real en Cajón"

    # 3. LA MAGIA: Calcular Diferencia y poner color
    def mostrar_diferencia(self, obj):
        if obj.saldo_final_real is None or obj.saldo_final_esperado is None:
            return "-"
        
        diferencia = obj.saldo_final_real - obj.saldo_final_esperado
        
        if diferencia == 0:
            color = "green"
            texto = "OK"
        elif diferencia < 0:
            color = "red"
            texto = f"Falta ${abs(diferencia)}"
        else:
            color = "blue" # O verde oscuro
            texto = f"Sobra ${diferencia}"

        # Devolvemos HTML para que se vea bonito en el panel
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            texto
        )
    mostrar_diferencia.short_description = "Balance"


# Registramos todo
admin.site.register(Categoria)
admin.site.register(Producto, ProductoAdmin)
admin.site.register(SesionCaja, SesionCajaAdmin)
admin.site.register(Venta, VentaAdmin)
admin.site.register(MovimientoCaja)