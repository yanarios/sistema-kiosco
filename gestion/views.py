import json
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from .models import Producto, Venta, DetalleVenta, SesionCaja, MovimientoCaja, Categoria
import pandas as pd 
from django.http import HttpResponse
from django.utils import timezone
from django.db.models import Sum
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
import datetime
from decimal import Decimal 
from .forms import ImportarProductosForm

@login_required
def ventas(request):
    
    caja_abierta = SesionCaja.objects.filter(estado=True).exists()

    productos = Producto.objects.filter(activo=True)
    
    
    categorias = Categoria.objects.all() 

    context = {
        'productos': productos,
        'caja_abierta': caja_abierta,
        'categorias': categorias, 
    }
    return render(request, 'gestion/ventas.html', context)


@login_required
def procesar_venta(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            items = data.get('items', [])
            metodo_pago = data.get('metodo_pago', 'EFECTIVO')
            
            if not items:
                return JsonResponse({'status': 'error', 'mensaje': 'El carrito está vacío'})

            with transaction.atomic():
                sesion_actual = SesionCaja.objects.filter(estado=True).last()
                
                if not sesion_actual:
                    return JsonResponse({'status': 'error', 'mensaje': 'No hay caja abierta. Abra una sesión primero.'})

                
                venta = Venta.objects.create(
                    sesion=sesion_actual,
                    total=0,
                    metodo_pago=metodo_pago
                )

                total_acumulado = 0

                for item in items:
                    producto = Producto.objects.get(id=item['id'])
                    
                    
                    cantidad = Decimal(str(item['cantidad'])) 
                    
                   
                    if producto.stock_actual < cantidad:
                         raise Exception(f"No hay suficiente stock de {producto.nombre}")

                    
                    subtotal = producto.precio_venta * cantidad
                    
                    DetalleVenta.objects.create(
                        venta=venta,
                        producto=producto,
                        cantidad=cantidad,
                        precio_unitario=producto.precio_venta,
                        subtotal=subtotal
                    )

                    
                    producto.stock_actual -= cantidad
                    producto.save()
                    
                    total_acumulado += subtotal

                venta.total = total_acumulado
                venta.save()

            
            return JsonResponse({
                'status': 'success', 
                'mensaje': 'Venta registrada OK', 
                'venta_id': venta.id 
            })

        except Exception as e:
            return JsonResponse({'status': 'error', 'mensaje': str(e)})
        
    
    return JsonResponse({'status': 'error', 'mensaje': 'Método no permitido'})

@login_required
def exportar_ventas_excel(request):
    
    ventas = Venta.objects.all().order_by('-fecha')

    
    data = []
    for v in ventas:
        
        fecha_local = timezone.localtime(v.fecha).strftime('%d/%m/%Y %H:%M')
        
        data.append({
            'ID Venta': v.id,
            'Fecha': fecha_local,
            'Cajero/Usuario': v.sesion.usuario.username,
            'Método Pago': v.metodo_pago,
            'Total': float(v.total), 
            'ID Sesión Caja': v.sesion.id
        })

    
    df = pd.DataFrame(data)

    
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="reporte_ventas.xlsx"'

    
    df.to_excel(response, index=False, engine='openpyxl')
    
    return response


@login_required
def apertura_caja(request):
    
    if SesionCaja.objects.filter(estado=True).exists():
        return redirect('ventas')

    if request.method == 'POST':
        saldo_inicial = request.POST.get('saldo_inicial', 0)
        
        
        SesionCaja.objects.create(
            usuario=request.user,
            saldo_inicial=saldo_inicial,
            estado=True
        )
        
        return redirect('ventas')

    return render(request, 'gestion/apertura_caja.html')



@login_required
def cierre_caja(request):
    sesion = SesionCaja.objects.filter(estado=True).last()
    if not sesion:
        return redirect('ventas')

    # --- GUARDADO DEL CIERRE ---
    if request.method == 'POST':
        efectivo = Decimal(request.POST.get('efectivo', 0))
        vales = Decimal(request.POST.get('vales', 0))
        debito = Decimal(request.POST.get('debito', 0))
        credito = Decimal(request.POST.get('credito', 0))

        sesion.monto_efectivo_real = efectivo
        sesion.monto_vales_real = vales
        sesion.monto_debito_real = debito
        sesion.monto_credito_real = credito
        
        # Total real
        sesion.saldo_final_real = efectivo + vales + debito + credito
        
        sesion.fecha_cierre = timezone.now()
        sesion.estado = False
        sesion.save()
        
        return redirect('ventas') # O reporte_mensual

    # --- CÁLCULOS PARA LA VALIDACIÓN (Escondidos en el HTML) ---
    
    # 1. Ventas desglosadas
    ventas_efectivo = sesion.ventas.filter(metodo_pago='EFECTIVO').aggregate(Sum('total'))['total__sum'] or 0
    ventas_vales = sesion.ventas.filter(metodo_pago='VALE').aggregate(Sum('total'))['total__sum'] or 0
    ventas_debito = sesion.ventas.filter(metodo_pago__in=['DEBITO', 'MERCADOPAGO']).aggregate(Sum('total'))['total__sum'] or 0
    ventas_credito = sesion.ventas.filter(metodo_pago='CREDITO').aggregate(Sum('total'))['total__sum'] or 0
    
    # Nota: Agrupé MercadoPago con Débito, si querés separarlo avisame.
    
    # 2. Movimientos de Caja
    ingresos = sesion.movimientos.filter(tipo='INGRESO').aggregate(Sum('monto'))['monto__sum'] or 0
    egresos = sesion.movimientos.filter(tipo='EGRESO').aggregate(Sum('monto'))['monto__sum'] or 0

    # 3. Cálculo de ESPERADOS (Lo que el sistema sabe)
    esperado_efectivo = sesion.saldo_inicial + ventas_efectivo + ingresos - egresos
    
    # Guardamos el esperado total para referencia
    sesion.saldo_final_esperado = esperado_efectivo 
    sesion.save()

    context = {
        'sesion': sesion,
        # Pasamos los valores esperados al template para que JS los use (ocultos)
        'esperado_efectivo': esperado_efectivo,
        'esperado_vales': ventas_vales,
        'esperado_debito': ventas_debito,
        'esperado_credito': ventas_credito,
        
        # Totales para el resumen visual de arriba
        'ventas_efectivo': ventas_efectivo,
        'ventas_digital': ventas_debito + ventas_credito,
    }
    return render(request, 'gestion/cierre_caja.html', context)

@login_required
def registrar_movimiento(request):
    if request.method == 'POST':
        caja = SesionCaja.objects.filter(estado=True).last()
        if not caja:
            
            return redirect('ventas')

        tipo = request.POST.get('tipo')
        categoria = request.POST.get('categoria') 
        monto = request.POST.get('monto')
        descripcion = request.POST.get('descripcion')

        MovimientoCaja.objects.create(
            sesion=caja,
            tipo=tipo,
            categoria=categoria, 
            monto=monto,
            descripcion=descripcion
        )
          
        messages.success(request, f"Movimiento registrado: {descripcion} (${monto})")

        return redirect('ventas')
    return redirect('ventas')


@login_required 
def exportar_productos_excel(request):
    
    if not request.user.is_staff:
        return redirect('ventas')

    productos = Producto.objects.filter(activo=True).order_by('nombre')

    data = []
    for p in productos:
        ganancia_unitaria = p.precio_venta - p.precio_costo
        valor_inventario = p.precio_costo * p.stock_actual 
        
        data.append({
            'Código': p.codigo,
            'Nombre': p.nombre,
            'Categoría': p.categoria.nombre if p.categoria else '-',
            'Costo ($)': float(p.precio_costo), 
            'Precio Venta ($)': float(p.precio_venta),
            'Ganancia x Unid ($)': float(ganancia_unitaria),
            'Stock': p.stock_actual,
            'Dinero Invertido ($)': float(valor_inventario)
        })

    df = pd.DataFrame(data)
    
    
    df = df[['Código', 'Nombre', 'Categoría', 'Costo ($)', 'Precio Venta ($)', 'Ganancia x Unid ($)', 'Stock', 'Dinero Invertido ($)']]

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="lista_precios_stock.xlsx"'
    df.to_excel(response, index=False, engine='openpyxl')
    
    return response



@login_required
def reporte_mensual(request):
    
    if not request.user.is_staff:
        return redirect('ventas')

    
    hoy = datetime.date.today()
    mes_actual = hoy.month
    anio_actual = hoy.year

    
    ventas = Venta.objects.filter(fecha__month=mes_actual, fecha__year=anio_actual)
    total_ventas = ventas.aggregate(Sum('total'))['total__sum'] or 0

    
    costo_mercaderia = 0
    cantidad_ventas = ventas.count()
    
    for venta in ventas:
        for detalle in venta.detalles.all():
            
            costo_mercaderia += detalle.producto.precio_costo * detalle.cantidad

    
    movimientos = MovimientoCaja.objects.filter(
        sesion__fecha_apertura__month=mes_actual, 
        sesion__fecha_apertura__year=anio_actual,
        tipo='EGRESO'
    )
    total_gastos = movimientos.aggregate(Sum('monto'))['monto__sum'] or 0

    
    ganancia_bruta = total_ventas - costo_mercaderia
    ganancia_neta = ganancia_bruta - total_gastos
    margin_rentabilidad = (ganancia_neta / total_ventas * 100) if total_ventas > 0 else 0

    context = {
        'mes': hoy.strftime("%B"), 
        'anio': anio_actual,
        'total_ventas': total_ventas,
        'costo_mercaderia': costo_mercaderia,
        'total_gastos': total_gastos,
        'ganancia_bruta': ganancia_bruta,
        'ganancia_neta': ganancia_neta,
        'margen': round(margin_rentabilidad, 1),
        'cantidad_ventas': cantidad_ventas
    }

    return render(request, 'gestion/reporte_mensual.html', context)


@login_required
def imprimir_ticket(request, venta_id):
    
    venta = Venta.objects.get(id=venta_id)
    items = DetalleVenta.objects.filter(venta=venta)
    
    context = {
        'venta': venta,
        'fecha': venta.fecha,
        'items': items,
        'total': venta.total,
        'metodo_pago': venta.metodo_pago
    }
    return render(request, 'gestion/ticket.html', context)



# --- IMPORTACIÓN MASIVA ---
@login_required
def importar_productos(request):
    if request.method == 'POST':
        form = ImportarProductosForm(request.POST, request.FILES)
        if form.is_valid():
            archivo = request.FILES['archivo_excel']
            try:
                # 1. Detectar si es Excel o CSV
                if archivo.name.endswith('.csv'):
                    df = pd.read_csv(archivo)
                else:
                    df = pd.read_excel(archivo)

                # 2. Normalizar columnas (minúsculas y sin espacios para evitar errores)
                df.columns = df.columns.str.strip().str.lower()

                # 3. Validar columnas obligatorias
                requeridas = ['codigo', 'nombre', 'venta']
                if not all(col in df.columns for col in requeridas):
                    messages.error(request, "❌ Error: El archivo DEBE tener las columnas: codigo, nombre, venta")
                    return render(request, 'gestion/importar.html', {'form': form})

                contador_nuevos = 0
                contador_actualizados = 0

                # 4. Transacción Atómica (Si falla uno, no se guarda nada a medias)
                with transaction.atomic():
                    for index, row in df.iterrows():
                        # Convertimos a string y limpiamos espacios
                        codigo = str(row['codigo']).strip().replace('.0', '') # Evita que 123 sea "123.0"
                        nombre = str(row['nombre']).strip()
                        
                        # Manejo de Categoría (Si no existe, la crea)
                        cat_nombre = str(row.get('categoria', 'General')).strip()
                        categoria_obj, _ = Categoria.objects.get_or_create(nombre=cat_nombre)

                        # Valores numéricos seguros
                        precio_venta = float(row['venta']) if pd.notna(row['venta']) else 0
                        precio_costo = float(row.get('costo', 0)) if pd.notna(row.get('costo')) else 0
                        stock = float(row.get('stock', 0)) if pd.notna(row.get('stock')) else 0

                        # CREAR O ACTUALIZAR PRODUCTO
                        producto, created = Producto.objects.update_or_create(
                            codigo=codigo,
                            defaults={
                                'nombre': nombre,
                                'precio_venta': precio_venta,
                                'precio_costo': precio_costo,
                                'stock_actual': stock, # OJO: Esto sobreescribe el stock. Si querés sumar, avisame.
                                'categoria': categoria_obj,
                                'activo': True
                            }
                        )
                        
                        if created:
                            contador_nuevos += 1
                        else:
                            contador_actualizados += 1

                messages.success(request, f"✅ Éxito: Se crearon {contador_nuevos} productos y se actualizaron {contador_actualizados}.")
                return redirect('ventas')

            except Exception as e:
                messages.error(request, f"🔥 Error crítico al procesar el archivo: {str(e)}")

    else:
        form = ImportarProductosForm()

    return render(request, 'gestion/importar.html', {'form': form})