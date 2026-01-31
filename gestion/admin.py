from django.contrib import admin
from django.utils.html import format_html
from .models import Producto, SesionCaja, Venta, DetalleVenta, MovimientoCaja, Categoria, Cliente

# 1. PRODUCTOS (Con tus colores de stock)
@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'codigo', 'precio_costo', 'precio_venta', 'stock_actual', 'mostrar_estado', 'activo')
    search_fields = ('nombre', 'codigo')
    list_filter = ('categoria', 'activo')
    list_editable = ('stock_actual', 'precio_venta', 'activo') # Para editar rápido
    
    def mostrar_estado(self, obj):
        if obj.stock_actual == 0:
            color = "red"
            texto = "⛔ AGOTADO"
        elif obj.stock_actual <= obj.stock_minimo:
            color = "orange"
            texto = "⚠️ BAJO"
        else:
            color = "green"
            texto = "✅ OK"
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, texto)
    mostrar_estado.short_description = "Estado Stock"

# 2. CATEGORÍAS
@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ('nombre',)

# 3. CLIENTES
@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'telefono', 'deuda_actual')
    search_fields = ('nombre',)

# 4. CAJAS (Con tu visualización de Balance + Seguridad Anti-Fraude)
@admin.register(SesionCaja)
class SesionCajaAdmin(admin.ModelAdmin):
    list_display = ('id', 'usuario', 'fecha_apertura', 'fecha_cierre', 'estado', 'mostrar_saldo_esperado', 'mostrar_saldo_real', 'mostrar_diferencia')
    list_filter = ('estado', 'usuario')
    date_hierarchy = 'fecha_apertura'
    
    # --- TUS FUNCIONES VISUALES ---
    def mostrar_saldo_esperado(self, obj):
        return f"${obj.saldo_final_esperado}" if obj.saldo_final_esperado is not None else "-"
    mostrar_saldo_esperado.short_description = "Esperado"

    def mostrar_saldo_real(self, obj):
        return f"${obj.saldo_final_real}" if obj.saldo_final_real is not None else "-"
    mostrar_saldo_real.short_description = "Real"

    def mostrar_diferencia(self, obj):
        if obj.saldo_final_real is None or obj.saldo_final_esperado is None:
            return "-"
        
        diferencia = obj.saldo_final_real - obj.saldo_final_esperado
        
        if abs(diferencia) < 1: # Margen de $1
            color = "green"
            texto = "✅ OK"
        elif diferencia < 0:
            color = "red"
            texto = f"Falta ${abs(diferencia)}"
        else:
            color = "blue"
            texto = f"Sobra ${diferencia}"

        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, texto)
    mostrar_diferencia.short_description = "Balance"

    # --- SEGURIDAD Y PERMISOS (LO NUEVO) ---
    
    # 1. No borrar cajas cerradas
    def has_delete_permission(self, request, obj=None):
        if obj and obj.estado == False:
            return False 
        return super().has_delete_permission(request, obj)

    # 2. Bloquear edición de números, permitir justificación
    def get_readonly_fields(self, request, obj=None):
        if obj and obj.estado == False:
            return ('usuario', 'fecha_apertura', 'fecha_cierre', 'saldo_inicial', 
                    'saldo_final_esperado', 'saldo_final_real', 
                    'monto_efectivo_real', 'monto_vales_real', 
                    'monto_debito_real', 'monto_credito_real')
        return ()

# 5. VENTAS (Solo Lectura Absoluta)
class DetalleVentaInline(admin.TabularInline):
    model = DetalleVenta
    readonly_fields = ('producto', 'cantidad', 'precio_unitario', 'subtotal')
    can_delete = False
    extra = 0

@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display = ('id', 'fecha', 'total', 'metodo_pago', 'usuario', 'cliente')
    list_filter = ('metodo_pago', 'usuario', 'fecha')
    search_fields = ('id', 'cliente__nombre')
    inlines = [DetalleVentaInline]
    
    # BLOQUEO TOTAL DE EDICIÓN
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False

# 6. MOVIMIENTOS (Solo Lectura)
@admin.register(MovimientoCaja)
class MovimientoCajaAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'tipo', 'categoria', 'monto', 'descripcion', 'sesion')
    list_filter = ('tipo', 'categoria')
    
    def has_change_permission(self, request, obj=None): return False