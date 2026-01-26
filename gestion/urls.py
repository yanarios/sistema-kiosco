from django.urls import path
from . import views

urlpatterns = [
    path('', views.ventas, name='ventas'),
    path('cobrar/', views.procesar_venta, name='procesar_venta'),
    path('exportar/', views.exportar_ventas_excel, name='exportar_excel'),
    path('cierre/', views.cierre_caja, name='cierre_caja'),
    path('apertura/', views.apertura_caja, name='apertura_caja'),
    path('movimiento/', views.registrar_movimiento, name='registrar_movimiento'),
    path('exportar-productos/', views.exportar_productos_excel, name='exportar_productos_excel'),
    path('reporte-mensual/', views.reporte_mensual, name='reporte_mensual'),
    path('ticket/<int:venta_id>/', views.imprimir_ticket, name='imprimir_ticket'),
]