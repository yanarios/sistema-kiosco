from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

# 1. CATEGORÍAS
class Categoria(models.Model):
    nombre = models.CharField(max_length=50)

    def __str__(self):
        return self.nombre

# 2. CLIENTES (NUEVO: Esto faltaba y daba error)
class Cliente(models.Model):
    nombre = models.CharField(max_length=100)
    telefono = models.CharField(max_length=50, blank=True, null=True)
    direccion = models.CharField(max_length=200, blank=True, null=True)
    deuda_actual = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.nombre} (Debe: ${self.deuda_actual})"

# 3. PRODUCTOS
class Producto(models.Model):
    codigo = models.CharField(max_length=50, unique=True, help_text="Código de barras o manual")
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True, null=True) 
    categoria = models.ForeignKey(Categoria, on_delete=models.SET_NULL, null=True, blank=True)

    TIPO_VENTA_CHOICES = [
        ('UNIDAD', 'Por Unidad (Ej: Alfajor)'),
        ('PESO', 'Por Peso/Kilo (Ej: Pan, Fiambre)'),
    ]
    tipo_venta = models.CharField(max_length=10, choices=TIPO_VENTA_CHOICES, default='UNIDAD')
    
    precio_costo = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Costo ($)")
    precio_venta = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Venta ($)")
    
    stock_actual = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    stock_minimo = models.IntegerField(default=5, help_text="Avisar cuando llegue a esta cantidad")
    
    activo = models.BooleanField(default=True)
    imagen = models.ImageField(upload_to='productos/', blank=True, null=True) 

    def __str__(self):
        return f"{self.nombre} (${self.precio_venta})"

# 4. SESIÓN DE CAJA
class SesionCaja(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)
    fecha_apertura = models.DateTimeField(auto_now_add=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    
    saldo_inicial = models.DecimalField(max_digits=12, decimal_places=2, help_text="Dinero en caja al abrir")
    
    # Lo que el sistema calcula que debería haber
    saldo_final_esperado = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    
    # El Total Real (Suma de los 4 campos de abajo)
    saldo_final_real = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    
    # --- DESGLOSE DEL CONTEO FÍSICO ---
    monto_efectivo_real = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Efectivo")
    monto_debito_real = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Débito")
    monto_credito_real = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Crédito")
    monto_vales_real = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Vales y Fiados")

    # Auditoría Dueña
    justificacion = models.TextField(blank=True, null=True, verbose_name="Notas de Auditoría (Dueña)", help_text="Usar para explicar faltantes o sobrantes.")

    estado = models.BooleanField(default=True, help_text="True si está abierta")
    
    def __str__(self):
        fecha_local = timezone.localtime(self.fecha_apertura)
        return f"Caja {self.id} - {self.usuario.username} ({fecha_local.strftime('%d/%m %H:%M')})"

# 5. VENTA
class Venta(models.Model):
    METODOS_PAGO = [
        ('EFECTIVO', 'Efectivo'),
        ('MERCADOPAGO', 'Mercado Pago'),
        ('DEBITO', 'Débito'),
        ('CREDITO', 'Crédito'),
        ('VALE', 'Vale / Fiado'), # AGREGADO: Opción Vale
    ]

    sesion = models.ForeignKey(SesionCaja, on_delete=models.PROTECT, related_name='ventas')
    usuario = models.ForeignKey(User, on_delete=models.PROTECT, null=True) # AGREGADO: Quién hizo la venta
    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True) # AGREGADO: Para el fiado
    
    fecha = models.DateTimeField(default=timezone.now)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    metodo_pago = models.CharField(max_length=20, choices=METODOS_PAGO, default='EFECTIVO')

    def __str__(self):
        return f"Venta #{self.id} - ${self.total}"

# 6. DETALLE DE VENTA
class DetalleVenta(models.Model):
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    
    # CAMBIO IMPORTANTE: PositiveIntegerField -> DecimalField
    # Esto permite vender "0.5" kg de Pan. Si es entero, solo podrías vender 1kg, 2kg, etc.
    cantidad = models.DecimalField(max_digits=10, decimal_places=3, default=1)
    
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2, help_text="Precio al momento de la venta")
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)

    def save(self, *args, **kwargs):
        # Calculamos subtotal multiplicando Decimal * Decimal (sin errores)
        self.subtotal = self.cantidad * self.precio_unitario
        super().save(*args, **kwargs)

# 7. MOVIMIENTOS
class MovimientoCaja(models.Model):
    TIPOS = [
        ('INGRESO', 'Ingreso (Cambio, etc)'),
        ('EGRESO', 'Egreso (Retiro, Pago Prov)'),
    ]

    CATEGORIA_CHOICES = [
        ('VENTA', 'Venta Automática'), 
        ('OTROS_INGRESOS', 'Otros Ingresos (Carga Virtual, etc)'),
        ('GASTO_FIJO', 'Gasto Fijo (Luz, Internet, Alquiler)'),
        ('GASTO_VARIO', 'Gasto Vario (Limpieza, Bolsitas)'),
        ('PROVEEDOR', 'Pago a Proveedores / Mercadería'),
        ('RETIRO_SOCIO', 'Retiro de Ganancia (Dueño)'),
    ]

    sesion = models.ForeignKey(SesionCaja, on_delete=models.PROTECT, related_name='movimientos')
    fecha = models.DateTimeField(auto_now_add=True)
    tipo = models.CharField(max_length=10, choices=TIPOS)
    categoria = models.CharField(max_length=20, choices=CATEGORIA_CHOICES, default='OTROS_INGRESOS')
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    descripcion = models.CharField(max_length=200)

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.get_categoria_display()}: ${self.monto}"