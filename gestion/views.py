import json
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from .models import Producto, Venta, DetalleVenta, SesionCaja, MovimientoCaja
import pandas as pd 
from django.http import HttpResponse
from django.utils import timezone
from django.db.models import Sum
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
import datetime
from decimal import Decimal


@login_required
def ventas(request):
    # 1. Verificamos si hay caja abierta, pero NO REDIRIGIMOS
    caja_abierta = SesionCaja.objects.filter(estado=True).exists()

    # 2. Traemos productos
    productos = Producto.objects.filter(activo=True)
    
    # 3. Pasamos el dato 'caja_abierta' al HTML
    context = {
        'productos': productos,
        'caja_abierta': caja_abierta, # <--- Esto es la clave
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

                # Creamos la Venta
                venta = Venta.objects.create(
                    sesion=sesion_actual,
                    total=0,
                    metodo_pago=metodo_pago
                )

                total_acumulado = 0

                for item in items:
                    producto = Producto.objects.get(id=item['id'])
                    
                    # --- CAMBIO CLAVE 1: Convertir a Decimal ---
                    # Usamos str() antes para asegurar precisión al convertir de float a Decimal
                    cantidad = Decimal(str(item['cantidad'])) 
                    
                    # Verificamos Stock
                    if producto.stock_actual < cantidad:
                         raise Exception(f"No hay suficiente stock de {producto.nombre}")

                    # Ahora sí podemos multiplicar Decimal * Decimal
                    subtotal = producto.precio_venta * cantidad
                    
                    DetalleVenta.objects.create(
                        venta=venta,
                        producto=producto,
                        cantidad=cantidad, # Usamos la variable convertida
                        precio_unitario=producto.precio_venta,
                        subtotal=subtotal
                    )

                    # Restamos Stock
                    producto.stock_actual -= cantidad
                    producto.save()
                    
                    total_acumulado += subtotal

                venta.total = total_acumulado
                venta.save()

            # --- CAMBIO CLAVE 2: Devolver el ID para el Ticket ---
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
    # 1. Buscamos las ventas (podrías filtrar por fecha aquí)
    ventas = Venta.objects.all().order_by('-fecha')

    # 2. Preparamos los datos para Pandas
    data = []
    for v in ventas:
        # Convertimos fecha a local para que salga bien en el Excel
        fecha_local = timezone.localtime(v.fecha).strftime('%d/%m/%Y %H:%M')
        
        data.append({
            'ID Venta': v.id,
            'Fecha': fecha_local,
            'Cajero/Usuario': v.sesion.usuario.username,
            'Método Pago': v.metodo_pago,
            'Total': float(v.total), # Convertir a float para que Excel sume bien
            'ID Sesión Caja': v.sesion.id
        })

    # 3. Creamos el DataFrame
    df = pd.DataFrame(data)

    # 4. Preparamos la respuesta HTTP para descargar archivo
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="reporte_ventas.xlsx"'

    # 5. Guardamos el Excel en la respuesta
    df.to_excel(response, index=False, engine='openpyxl')
    
    return response


@login_required
def apertura_caja(request):
    # Si ya hay una abierta, no tiene sentido estar acá -> Mandalo a vender
    if SesionCaja.objects.filter(estado=True).exists():
        return redirect('ventas')

    if request.method == 'POST':
        saldo_inicial = request.POST.get('saldo_inicial', 0)
        
        # Creamos la sesión nueva
        SesionCaja.objects.create(
            usuario=request.user,
            saldo_inicial=saldo_inicial,
            estado=True
        )
        # Ahora sí, a vender
        return redirect('ventas')

    return render(request, 'gestion/apertura_caja.html')



@login_required
def cierre_caja(request):
    sesion = SesionCaja.objects.filter(estado=True).last()
    if not sesion:
        return redirect('ventas')

    if request.method == 'POST':
        # ... (esta parte queda igual) ...
        dinero_real = float(request.POST.get('dinero_real', 0))
        sesion.saldo_final_real = dinero_real
        sesion.fecha_cierre = timezone.now()
        sesion.estado = False
        sesion.save()
        return redirect('ventas')

    # --- CÁLCULOS ACTUALIZADOS ---
    total_ventas_efectivo = sesion.ventas.filter(metodo_pago='EFECTIVO').aggregate(Sum('total'))['total__sum'] or 0
    total_ventas_digital = sesion.ventas.exclude(metodo_pago='EFECTIVO').aggregate(Sum('total'))['total__sum'] or 0
    
    # Sumar Ingresos y Egresos
    total_ingresos = sesion.movimientos.filter(tipo='INGRESO').aggregate(Sum('monto'))['monto__sum'] or 0
    total_egresos = sesion.movimientos.filter(tipo='EGRESO').aggregate(Sum('monto'))['monto__sum'] or 0

    # Fórmula Final
    saldo_esperado = sesion.saldo_inicial + total_ventas_efectivo + total_ingresos - total_egresos
    
    sesion.saldo_final_esperado = saldo_esperado
    sesion.save()

    context = {
        'sesion': sesion,
        'ventas_efectivo': total_ventas_efectivo,
        'ventas_digital': total_ventas_digital,
        'ingresos': total_ingresos,   # Pasalo al HTML si querés mostrarlo
        'egresos': total_egresos,     # Pasalo al HTML si querés mostrarlo
        'saldo_esperado': saldo_esperado,
    }
    return render(request, 'gestion/cierre_caja.html', context)


@login_required
def registrar_movimiento(request):
    if request.method == 'POST':
        sesion = SesionCaja.objects.filter(estado=True).last()
        if not sesion:
            return redirect('ventas') # Seguridad

        monto = request.POST.get('monto')
        tipo = request.POST.get('tipo') # 'INGRESO' o 'EGRESO'
        descripcion = request.POST.get('descripcion')

        # Guardamos el movimiento
        MovimientoCaja.objects.create(
            sesion=sesion,
            tipo=tipo,
            monto=monto,
            descripcion=descripcion
        )
        
        # Mensaje de confirmación (opcional, pero queda lindo)
        messages.success(request, f"Movimiento registrado: {descripcion} (${monto})")
        
        return redirect('ventas')
        
    return redirect('ventas')


@login_required # Asegurate de tener esto si lo restringiste
def exportar_productos_excel(request):
    # Verificamos que sea staff si querés protegerlo
    if not request.user.is_staff:
        return redirect('ventas')

    productos = Producto.objects.filter(activo=True).order_by('nombre')

    data = []
    for p in productos:
        # --- CORRECCIÓN AQUÍ ---
        # Antes decía p.precio_compra, ahora debe decir p.precio_costo
        ganancia_unitaria = p.precio_venta - p.precio_costo
        valor_inventario = p.precio_costo * p.stock_actual 
        
        data.append({
            'Código': p.codigo,
            'Nombre': p.nombre,
            'Categoría': p.categoria.nombre if p.categoria else '-',
            'Costo ($)': float(p.precio_costo), # <--- AQUÍ TAMBIÉN
            'Precio Venta ($)': float(p.precio_venta),
            'Ganancia x Unid ($)': float(ganancia_unitaria),
            'Stock': p.stock_actual,
            'Dinero Invertido ($)': float(valor_inventario)
        })

    df = pd.DataFrame(data)
    
    # Ordenamos columnas
    df = df[['Código', 'Nombre', 'Categoría', 'Costo ($)', 'Precio Venta ($)', 'Ganancia x Unid ($)', 'Stock', 'Dinero Invertido ($)']]

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="lista_precios_stock.xlsx"'
    df.to_excel(response, index=False, engine='openpyxl')
    
    return response



@login_required
def reporte_mensual(request):
    # Solo permitido para Staff/Dueño
    if not request.user.is_staff:
        return redirect('ventas')

    # Definimos el mes actual (o podrías recibirlo por parámetro para filtrar)
    hoy = datetime.date.today()
    mes_actual = hoy.month
    anio_actual = hoy.year

    # 1. Total de Ventas del mes
    ventas = Venta.objects.filter(fecha__month=mes_actual, fecha__year=anio_actual)
    total_ventas = ventas.aggregate(Sum('total'))['total__sum'] or 0

    # 2. Costo de la Mercadería Vendida (CMV)
    # Como no guardamos el costo histórico, usamos el costo actual del producto (Estimación)
    costo_mercaderia = 0
    cantidad_ventas = ventas.count()
    
    for venta in ventas:
        for detalle in venta.detalles.all():
            # Costo * Cantidad vendida
            costo_mercaderia += detalle.producto.precio_costo * detalle.cantidad

    # 3. Gastos registrados en la caja (Egresos)
    # Filtramos sesiones de este mes y sus movimientos tipo EGRESO
    movimientos = MovimientoCaja.objects.filter(
        sesion__fecha_apertura__month=mes_actual, 
        sesion__fecha_apertura__year=anio_actual,
        tipo='EGRESO'
    )
    total_gastos = movimientos.aggregate(Sum('monto'))['monto__sum'] or 0

    # 4. Cálculo Final
    ganancia_bruta = total_ventas - costo_mercaderia
    ganancia_neta = ganancia_bruta - total_gastos
    margin_rentabilidad = (ganancia_neta / total_ventas * 100) if total_ventas > 0 else 0

    context = {
        'mes': hoy.strftime("%B"), # Nombre del mes
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


    # gestion/views.py

@login_required
def imprimir_ticket(request, venta_id):
    # Buscamos la venta específica
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