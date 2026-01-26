from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class Categoria(models.Model):
    nombre = models.CharField(max_length=50)

    def __str__(self):
        return self.nombre

class Producto(models.Model):
    codigo = models.CharField(max_length=50, unique=True, help_text="Código de barras o manual")
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True, null=True) # Agregamos esto por si querés detalles
    categoria = models.ForeignKey(Categoria, on_delete=models.SET_NULL, null=True, blank=True)

    TIPO_VENTA_CHOICES = [
        ('UNIDAD', 'Por Unidad (Ej: Alfajor)'),
        ('PESO', 'Por Peso/Kilo (Ej: Pan, Fiambre)'),
    ]
    tipo_venta = models.CharField(max_length=10, choices=TIPO_VENTA_CHOICES, default='UNIDAD')

    # ... precios ...
    
    # Precios
    precio_costo = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Costo ($)")
    precio_venta = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Venta ($)")
    
    # Stock
    stock_actual = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    stock_minimo = models.IntegerField(default=5, help_text="Avisar cuando llegue a esta cantidad")
    
    # Extras
    activo = models.BooleanField(default=True)
    imagen = models.ImageField(upload_to='productos/', blank=True, null=True) # Opcional: para ver foto en el admin

    def __str__(self):
        return f"{self.nombre} (${self.precio_venta})"

class SesionCaja(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)
    fecha_apertura = models.DateTimeField(auto_now_add=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    saldo_inicial = models.DecimalField(max_digits=12, decimal_places=2, help_text="Dinero en caja al abrir")
    saldo_final_esperado = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Calculado por el sistema")
    saldo_final_real = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Lo que contó el cajero")
    estado = models.BooleanField(default=True, help_text="True si está abierta")
    
    def __str__(self):
        fecha_local = timezone.localtime(self.fecha_apertura)
        return f"Caja {self.id} - {self.usuario.username} ({fecha_local.strftime('%d/%m %H:%M')})"

class Venta(models.Model):
    METODOS_PAGO = [
        ('EFECTIVO', 'Efectivo'),
        ('MERCADOPAGO', 'Mercado Pago'),
        ('DEBITO', 'Débito'),
        ('CREDITO', 'Crédito'),
    ]

    sesion = models.ForeignKey(SesionCaja, on_delete=models.PROTECT, related_name='ventas')
    fecha = models.DateTimeField(default=timezone.now)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    metodo_pago = models.CharField(max_length=20, choices=METODOS_PAGO, default='EFECTIVO')

    def __str__(self):
        return f"Venta #{self.id} - ${self.total}"

class DetalleVenta(models.Model):
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField(default=1)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2, help_text="Precio al momento de la venta")
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)

    def save(self, *args, **kwargs):
        self.subtotal = self.cantidad * self.precio_unitario
        super().save(*args, **kwargs)

class MovimientoCaja(models.Model):
    TIPOS = [
        ('INGRESO', 'Ingreso (Cambio, etc)'),
        ('EGRESO', 'Egreso (Retiro, Pago Prov)'),
    ]
    sesion = models.ForeignKey(SesionCaja, on_delete=models.PROTECT, related_name='movimientos')
    fecha = models.DateTimeField(auto_now_add=True)
    tipo = models.CharField(max_length=10, choices=TIPOS)
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    descripcion = models.CharField(max_length=200)

    def __str__(self):
        return f"{self.tipo}: ${self.monto}"