from __future__ import annotations

import os
import re
import sqlite3
import json
import html
import secrets
import smtplib
import shutil
import tempfile
import zipfile
from email.message import EmailMessage
from email.utils import parseaddr
from cryptography.fernet import Fernet
import base64
import hashlib
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, datetime, timedelta
from pathlib import Path
from functools import wraps, lru_cache
from urllib.parse import urlparse, urlencode
from urllib import request as urlrequest, error as urlerror

from geopy.distance import geodesic
from geopy.geocoders import Nominatim

from flask import Flask, Response, render_template, render_template_string, request, redirect, url_for, session, flash, abort, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get('DATA_DIR', str(BASE_DIR / 'data')))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(os.environ.get('DATABASE_PATH', str(DATA_DIR / 'rds_core_web.db')))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
EMAIL_CONFIG_PATH = DATA_DIR / 'email_runtime_config.json'

APP_NAME = 'Operational LedgerFlow'
APP_SUBTITLE = 'Operational command for growing service businesses'
BRAND_TAGLINE = 'Jobs, dispatch, scheduling, and team coordination for service businesses.'
BRAND_LOGO_FILENAME = 'ledgerflow-logo.png'
BRAND_MARK_FILENAME = 'ledgerflow-mark.png'
TRACKING_PIXEL_GIF = base64.b64decode('R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==')
ADMIN_LABEL = 'Businesses'
CUSTOMER_LABEL = 'Customers'
DEFAULT_HOME_ADDRESS = '3934 Brookside Dr, Sarasota, FL 34231'
IRS_MILEAGE_RATE = 0.725
SELF_EMPLOYMENT_TAX_RATE = 0.153
W2_PAYROLL_TAX_RATE = 0.0765
FEDERAL_WITHHOLDING_RATE = 0.10
SOCIAL_SECURITY_RATE = 0.062
MEDICARE_RATE = 0.0145
ADDITIONAL_MEDICARE_RATE = 0.009
ROAD_FACTOR = 1.18
RDS_ADDRESS = DEFAULT_HOME_ADDRESS + ', United States'

PAYROLL_PERIODS = {
    'weekly': 52,
    'biweekly': 26,
    'semimonthly': 24,
    'monthly': 12,
}

OPS_DEFAULT_SERVICE_TYPES = [
    {
        'name': 'Cleaning',
        'description': 'Recurring or one-time residential and commercial cleaning work.',
        'default_duration_minutes': 180,
        'default_priority': 'normal',
        'default_crew_size': 2,
        'color_token': '#4F7363',
    },
    {
        'name': 'Painting',
        'description': 'Interior or exterior painting projects with prep and finish stages.',
        'default_duration_minutes': 360,
        'default_priority': 'high',
        'default_crew_size': 2,
        'color_token': '#C77647',
    },
    {
        'name': 'Landscaping',
        'description': 'Recurring lawn and landscaping visits with route-based scheduling.',
        'default_duration_minutes': 120,
        'default_priority': 'normal',
        'default_crew_size': 2,
        'color_token': '#4C8A57',
    },
    {
        'name': 'Mobile Detailing',
        'description': 'On-site vehicle detailing and care appointments.',
        'default_duration_minutes': 150,
        'default_priority': 'normal',
        'default_crew_size': 1,
        'color_token': '#5678A8',
    },
    {
        'name': 'Electrical',
        'description': 'Field-service electrical dispatches and job-site work.',
        'default_duration_minutes': 180,
        'default_priority': 'urgent',
        'default_crew_size': 1,
        'color_token': '#E3A94D',
    },
    {
        'name': 'Flooring',
        'description': 'Install, repair, and finish work for flooring crews.',
        'default_duration_minutes': 300,
        'default_priority': 'high',
        'default_crew_size': 2,
        'color_token': '#8B6E5D',
    },
    {
        'name': 'Custom',
        'description': 'Flexible service type for business-specific operational work.',
        'default_duration_minutes': 120,
        'default_priority': 'normal',
        'default_crew_size': 1,
        'color_token': '#72819A',
    },
]

DEFAULT_TAX_RULES = {
    2026: {
        'social_security_rate_employee': 0.062,
        'social_security_rate_employer': 0.062,
        'social_security_wage_base': 184500.0,
        'medicare_rate_employee': 0.0145,
        'medicare_rate_employer': 0.0145,
        'additional_medicare_rate': 0.009,
        'additional_medicare_threshold': 200000.0,
        'standard_deduction_single': 16100.0,
        'standard_deduction_married': 32200.0,
        'standard_deduction_head': 24150.0,
        'brackets_single_json': json.dumps([[0,0.10],[12400,0.12],[50400,0.22],[105700,0.24],[201775,0.32],[256225,0.35],[640600,0.37]]),
        'brackets_married_json': json.dumps([[0,0.10],[24800,0.12],[100800,0.22],[211400,0.24],[403550,0.32],[512450,0.35],[768700,0.37]]),
        'brackets_head_json': json.dumps([[0,0.10],[17000,0.12],[64850,0.22],[103350,0.24],[197300,0.32],[250500,0.35],[626350,0.37]]),
    }
}

BUSINESS_COLORS = ['#2563eb', '#7c3aed', '#ea580c', '#0ea5e9', '#16a34a', '#db2777', '#9333ea', '#0891b2']
LANGUAGE_OPTIONS = [
    ('en', 'English'),
    ('es', 'Español'),
    ('pt', 'Português'),
]
TRANSLATIONS = {
    'Language': {'es': 'Idioma', 'pt': 'Idioma'},
    'Save Language': {'es': 'Guardar idioma', 'pt': 'Salvar idioma'},
    'Logout': {'es': 'Cerrar sesión', 'pt': 'Sair'},
    'Worker Login': {'es': 'Acceso del trabajador', 'pt': 'Login do trabalhador'},
    'Create Account': {'es': 'Crear cuenta', 'pt': 'Criar conta'},
    'Welcome': {'es': 'Bienvenido', 'pt': 'Bem-vindo'},
    'Administrator-Made Software': {'es': 'Software creado por administradores', 'pt': 'Software feito por administradores'},
    'Professional billing, payroll tax readiness, calendar planning, and business financial management in one administrator-made platform.': {
        'es': 'FacturaciÃ³n profesional, preparaciÃ³n de impuestos de nÃ³mina, planificaciÃ³n de calendario y gestiÃ³n financiera empresarial en una sola plataforma creada por administradores.',
        'pt': 'Faturamento profissional, prontidÃ£o para impostos sobre a folha, planejamento de calendÃ¡rio e gestÃ£o financeira empresarial em uma Ãºnica plataforma feita por administradores.',
    },
    'Welcome to': {'es': 'Bienvenido a', 'pt': 'Bem-vindo ao'},
    'Welcome Administrator': {'es': 'Bienvenido administrador', 'pt': 'Bem-vindo administrador'},
    'Sign in to {app_name}': {'es': 'Inicia sesión en {app_name}', 'pt': 'Entre em {app_name}'},
    'Secure administrator and business access for the full financial workspace.': {
        'es': 'Acceso seguro para administradores y empresas al espacio financiero completo.',
        'pt': 'Acesso seguro para administradores e empresas ao espaço financeiro completo.',
    },
    'First launch detected. Create the administrator account for this isolated production deployment.': {
        'es': 'Se detectó el primer inicio. Crea la cuenta de administrador para esta implementación aislada.',
        'pt': 'Primeiro acesso detectado. Crie a conta de administrador para esta implantação isolada.',
    },
    'Full Name': {'es': 'Nombre completo', 'pt': 'Nome completo'},
    'Email': {'es': 'Correo electrónico', 'pt': 'E-mail'},
    'Password': {'es': 'Contraseña', 'pt': 'Senha'},
    'Confirm Password': {'es': 'Confirmar contraseña', 'pt': 'Confirmar senha'},
    'Create Administrator Account': {'es': 'Crear cuenta de administrador', 'pt': 'Criar conta de administrador'},
    'Sign In': {'es': 'Iniciar sesión', 'pt': 'Entrar'},
    'Forgot Password?': {'es': '¿Olvidaste tu contraseña?', 'pt': 'Esqueceu sua senha?'},
    'Business accounts are created through administrator invite links. Use your invite email to create your login.': {
        'es': 'Las cuentas empresariales se crean mediante enlaces de invitación del administrador. Usa el correo de tu invitación para crear tu acceso.',
        'pt': 'As contas empresariais são criadas por links de convite do administrador. Use o e-mail do convite para criar seu acesso.',
    },
    'Worker Portal': {'es': 'Portal del trabajador', 'pt': 'Portal do trabalhador'},
    'Welcome Worker': {'es': 'Bienvenido trabajador', 'pt': 'Bem-vindo trabalhador'},
    'Secure worker access for time, schedule, pay stubs, and notices.': {
        'es': 'Acceso seguro del trabajador para tiempo, horario, comprobantes y avisos.',
        'pt': 'Acesso seguro do trabalhador para horas, agenda, comprovantes e avisos.',
    },
    'Return to Main Portal': {'es': 'Volver al portal principal', 'pt': 'Voltar ao portal principal'},
    'RESTRICTED WORKER ACCESS': {'es': 'ACCESO RESTRINGIDO DEL TRABAJADOR', 'pt': 'ACESSO RESTRITO DO TRABALHADOR'},
    'NEED ADMIN OR BUSINESS LOGIN?': {'es': 'Â¿NECESITAS ACCESO DE ADMINISTRADOR O EMPRESA?', 'pt': 'PRECISA DE ACESSO DE ADMINISTRADOR OU EMPRESA?'},
    'Use the main LedgerFlow portal for administrator and business access.': {
        'es': 'Usa el portal principal de LedgerFlow para acceso de administrador y empresa.',
        'pt': 'Use o portal principal da LedgerFlow para acesso de administrador e empresa.',
    },
    'If you landed here by mistake, use the return button above or below this sign-in form.': {
        'es': 'Si llegaste aquÃ­ por error, usa el botÃ³n de regreso arriba o debajo de este formulario.',
        'pt': 'Se vocÃª chegou aqui por engano, use o botÃ£o de retorno acima ou abaixo deste formulÃ¡rio.',
    },
    'Sign In to Worker Portal': {'es': 'Entrar al portal del trabajador', 'pt': 'Entrar no portal do trabalhador'},
    'Business Setup': {'es': 'Configuración del negocio', 'pt': 'Configuração do negócio'},
    'Set up your LedgerFlow workspace': {'es': 'Configura tu espacio LedgerFlow', 'pt': 'Configure seu espaço LedgerFlow'},
    'Complete your business profile, choose your subscription tier, add your method on file, and unlock full access.': {
        'es': 'Completa el perfil de tu negocio, elige tu suscripción, agrega tu método registrado y desbloquea el acceso completo.',
        'pt': 'Complete o perfil da empresa, escolha sua assinatura, adicione o método salvo e desbloqueie o acesso completo.',
    },
    'Business Information': {'es': 'Información del negocio', 'pt': 'Informações da empresa'},
    'Subscription Setup': {'es': 'Configuración de suscripción', 'pt': 'Configuração da assinatura'},
    'Method On File': {'es': 'Método registrado', 'pt': 'Método registrado'},
    'Finish Setup': {'es': 'Finalizar configuración', 'pt': 'Finalizar configuração'},
    'Preferred Language': {'es': 'Idioma preferido', 'pt': 'Idioma preferido'},
    'Unlock workspace': {'es': 'Desbloquear espacio', 'pt': 'Desbloquear espaço'},
    'Complete Setup & Unlock Workspace': {'es': 'Completar configuración y desbloquear espacio', 'pt': 'Concluir configuração e desbloquear espaço'},
    'Finish Later': {'es': 'Terminar después', 'pt': 'Concluir depois'},
    'Administrator Dashboard': {'es': 'Panel del administrador', 'pt': 'Painel do administrador'},
    'Business Workspace': {'es': 'Espacio empresarial', 'pt': 'Espaço empresarial'},
    'Businesses': {'es': 'Empresas', 'pt': 'Empresas'},
    'Business Users': {'es': 'Usuarios empresariales', 'pt': 'Usuários empresariais'},
    'Email Settings': {'es': 'Configuración de correo', 'pt': 'Configuração de e-mail'},
    'AI Guide Settings': {'es': 'Configuración de la guía IA', 'pt': 'Configuração do guia de IA'},
    'Calendar': {'es': 'Calendario', 'pt': 'Calendário'},
    'Admin Tasks': {'es': 'Tareas administrativas', 'pt': 'Tarefas administrativas'},
    'Overview': {'es': 'Resumen', 'pt': 'Visão geral'},
    'Welcome Center': {'es': 'Centro de bienvenida', 'pt': 'Central de boas-vindas'},
    'Summary': {'es': 'Resumen', 'pt': 'Resumo'},
    'Income Records': {'es': 'Registros de ingresos', 'pt': 'Registros de receita'},
    'Team Members': {'es': 'Miembros del equipo', 'pt': 'Membros da equipe'},
    'Team Member Payouts': {'es': 'Pagos del equipo', 'pt': 'Pagamentos da equipe'},
    'Billing': {'es': 'Facturación', 'pt': 'Faturamento'},
    'Work Schedule': {'es': 'Programa de trabajo', 'pt': 'Agenda de trabalho'},
    'Reports': {'es': 'Reportes', 'pt': 'Relatórios'},
    'Operations Overview': {'es': 'Resumen operativo', 'pt': 'Visão operacional'},
    'Clients & Sales': {'es': 'Clientes y ventas', 'pt': 'Clientes e vendas'},
    'Expense Tracking': {'es': 'Control de gastos', 'pt': 'Controle de despesas'},
    'Gas': {'es': 'Gasolina', 'pt': 'Combustível'},
    'Materials': {'es': 'Materiales', 'pt': 'Materiais'},
    'Mileage': {'es': 'Millaje', 'pt': 'Quilometragem'},
    'Other Expenses': {'es': 'Otros gastos', 'pt': 'Outras despesas'},
    'Support': {'es': 'Soporte', 'pt': 'Suporte'},
    'Business Profile': {'es': 'Perfil del negocio', 'pt': 'Perfil da empresa'},
    'Benefits & Obligations': {'es': 'Beneficios y obligaciones', 'pt': 'Benefícios e obrigações'},
    'IRS Tips': {'es': 'Consejos del IRS', 'pt': 'Dicas do IRS'},
    'Help': {'es': 'Ayuda', 'pt': 'Ajuda'},
    'Team Member Portal': {'es': 'Portal del equipo', 'pt': 'Portal da equipe'},
    'Restricted Team Member Portal': {'es': 'Portal restringido del equipo', 'pt': 'Portal restrito da equipe'},
    'Work': {'es': 'Trabajo', 'pt': 'Trabalho'},
    'Time Summary': {'es': 'Resumen de tiempo', 'pt': 'Resumo de horas'},
    'Pay Stubs': {'es': 'Comprobantes de pago', 'pt': 'Comprovantes de pagamento'},
    'Schedule': {'es': 'Horario', 'pt': 'Agenda'},
    'Time Off Request': {'es': 'Solicitud de tiempo libre', 'pt': 'Solicitação de folga'},
    'Communication': {'es': 'Comunicación', 'pt': 'Comunicação'},
    'Policies & Notices': {'es': 'Políticas y avisos', 'pt': 'Políticas e avisos'},
    'Step 1 of 1': {'es': 'Paso 1 de 1', 'pt': 'Etapa 1 de 1'},
    'Create your business profile': {'es': 'Crea el perfil de tu negocio', 'pt': 'Crie o perfil da sua empresa'},
    'Choose subscription tier': {'es': 'Elige tu plan de suscripciÃ³n', 'pt': 'Escolha o plano da assinatura'},
    'Set method on file': {'es': 'Define o mÃ©todo registrado', 'pt': 'Defina o mÃ©todo salvo'},
    'Business Name': {'es': 'Nombre del negocio', 'pt': 'Nome da empresa'},
    'Business Type': {'es': 'Tipo de negocio', 'pt': 'Tipo de empresa'},
    'Business Structure': {'es': 'Estructura del negocio', 'pt': 'Estrutura da empresa'},
    'Kind of Business': {'es': 'Clase de negocio', 'pt': 'Tipo de negocio'},
    'Specialty / Short Description': {'es': 'Especialidad / descripcion corta', 'pt': 'Especialidade / descricao curta'},
    'Additional Owners / Owner Contacts': {'es': 'Propietarios adicionales / contactos de propietarios', 'pt': 'Proprietarios adicionais / contatos de proprietarios'},
    'Job Scope / Service Scope': {'es': 'Alcance del trabajo / alcance del servicio', 'pt': 'Escopo do trabalho / escopo do servico'},
    'Not added yet': {'es': 'Aun no agregado', 'pt': 'Ainda nao adicionado'},
    'Select one (optional)': {'es': 'Seleccione uno (opcional)', 'pt': 'Selecione um (opcional)'},
    'Business name, kind of business, structure, contact, language, EIN, address, and any helpful billing notes.': {
        'es': 'Nombre, tipo de negocio, estructura, contacto, idioma, EIN, direccion y notas utiles.',
        'pt': 'Nome, tipo de negocio, estrutura, contato, idioma, EIN, endereco e notas uteis.',
    },
    'Business name, kind of business, structure, contact, language, EIN, address, and admin notes.': {
        'es': 'Nombre, tipo de negocio, estructura, contacto, idioma, EIN, direccion y notas administrativas.',
        'pt': 'Nome, tipo de negocio, estrutura, contato, idioma, EIN, endereco e notas administrativas.',
    },
    'Used to personalize your welcome guidance, tips, and future recommendations.': {
        'es': 'Se usa para personalizar la bienvenida, consejos y recomendaciones futuras.',
        'pt': 'Usado para personalizar a boas-vindas, dicas e recomendacoes futuras.',
    },
    'Add one owner per line or include name, role, phone, and email.': {
        'es': 'Agrega un propietario por linea o incluye nombre, rol, telefono y correo.',
        'pt': 'Adicione um proprietario por linha ou inclua nome, funcao, telefone e e-mail.',
    },
    'Add one job scope per line so estimates, schedules, and future job templates can reuse the wording.': {
        'es': 'Agrega un alcance de trabajo por linea para reutilizarlo en presupuestos, agendas y futuras plantillas.',
        'pt': 'Adicione um escopo de trabalho por linha para reutilizar em orcamentos, agendas e futuros modelos.',
    },
    'Example: exterior wash and wax, ceramic coating, interior detailing': {
        'es': 'Ejemplo: lavado exterior y encerado, recubrimiento ceramico, detallado interior',
        'pt': 'Exemplo: lavagem externa e enceramento, revestimento ceramico, detalhamento interno',
    },
    'Optional short description like house cleaning, interior painting, gel nails, or prenatal massage': {
        'es': 'Descripcion opcional como limpieza de casas, pintura interior, unas en gel o masaje prenatal',
        'pt': 'Descricao opcional como limpeza residencial, pintura interna, unhas em gel ou massagem pre-natal',
    },
    'Your business profile is currently tailored around': {
        'es': 'El perfil de su negocio esta adaptado actualmente a',
        'pt': 'O perfil da sua empresa esta atualmente adaptado a',
    },
    'your service category': {'es': 'su categoria de servicio', 'pt': 'sua categoria de servico'},
    'Primary Contact Name': {'es': 'Nombre del contacto principal', 'pt': 'Nome do contato principal'},
    'Business Email': {'es': 'Correo del negocio', 'pt': 'E-mail da empresa'},
    'Business Phone': {'es': 'TelÃ©fono del negocio', 'pt': 'Telefone da empresa'},
    'Business Address': {'es': 'DirecciÃ³n del negocio', 'pt': 'EndereÃ§o da empresa'},
    'Billing Notes (optional)': {'es': 'Notas de facturaciÃ³n (opcional)', 'pt': 'Notas de faturamento (opcional)'},
    'Required': {'es': 'Requerido', 'pt': 'ObrigatÃ³rio'},
    'Choose Your Tier': {'es': 'Elige tu plan', 'pt': 'Escolha seu plano'},
    'Plan Code': {'es': 'CÃ³digo del plan', 'pt': 'CÃ³digo do plano'},
    'Monthly Subscription': {'es': 'SuscripciÃ³n mensual', 'pt': 'Assinatura mensal'},
    'Billing Start Date': {'es': 'Fecha de inicio de facturaciÃ³n', 'pt': 'Data inicial de faturamento'},
    'Keep this method on file for subscription billing.': {
        'es': 'MantÃ©n este mÃ©todo registrado para la facturaciÃ³n de la suscripciÃ³n.',
        'pt': 'Mantenha este mÃ©todo salvo para a cobranÃ§a da assinatura.',
    },
    'Unlock Access': {'es': 'Desbloquear acceso', 'pt': 'Desbloquear acesso'},
    'Administrator Workspace': {'es': 'Espacio del administrador', 'pt': 'EspaÃ§o do administrador'},
    'Administrator': {'es': 'Administrador', 'pt': 'Administrador'},
    'Workspace': {'es': 'Espacio', 'pt': 'EspaÃ§o'},
    'Reference': {'es': 'Referencia', 'pt': 'ReferÃªncia'},
    'Switch Business': {'es': 'Cambiar empresa', 'pt': 'Trocar empresa'},
    'Continue Setup': {'es': 'Continuar configuraciÃ³n', 'pt': 'Continuar configuraÃ§Ã£o'},
    'Complete onboarding to unlock your full LedgerFlow workspace.': {
        'es': 'Completa la incorporaciÃ³n para desbloquear todo tu espacio LedgerFlow.',
        'pt': 'Conclua a integraÃ§Ã£o para desbloquear todo o seu espaÃ§o LedgerFlow.',
    },
    'Search less. Navigate faster. Keep the work area centered.': {
        'es': 'Busca menos. Navega mÃ¡s rÃ¡pido. MantÃ©n el Ã¡rea de trabajo centrada.',
        'pt': 'Pesquise menos. Navegue mais rÃ¡pido. Mantenha a Ã¡rea de trabalho centralizada.',
    },
    'Your full LedgerFlow workspace in one navigation rail.': {
        'es': 'Todo tu espacio LedgerFlow en una sola barra de navegaciÃ³n.',
        'pt': 'Todo o seu espaÃ§o LedgerFlow em uma Ãºnica navegaÃ§Ã£o lateral.',
    },
}

TRANSLATIONS.update({
    'Payroll': {'es': 'Nomina', 'pt': 'Folha'},
    'Tax Ready': {'es': 'Listo para impuestos', 'pt': 'Pronto para impostos'},
    'Administrator Fees': {'es': 'Cargos del administrador', 'pt': 'Taxas do administrador'},
    'Marketing Video Coming Soon': {'es': 'Video de marketing proximamente', 'pt': 'Video de marketing em breve'},
    'Mobile experience update': {'es': 'Actualizacion de experiencia movil', 'pt': 'Atualizacao da experiencia mobile'},
    "We're still working here for you. The phone version will be ready soon.": {
        'es': 'Todavia estamos trabajando aqui para usted. La version para telefono estara lista pronto.',
        'pt': 'Ainda estamos trabalhando aqui para voce. A versao para telefone estara pronta em breve.',
    },
    'Home': {'es': 'Inicio', 'pt': 'Inicio'},
    'Sales': {'es': 'Ventas', 'pt': 'Vendas'},
    'Pay': {'es': 'Pagar', 'pt': 'Pagar'},
    'View': {'es': 'Ver', 'pt': 'Ver'},
    'Disclaimer': {'es': 'Descargo', 'pt': 'Aviso legal'},
    'Client Workspace': {'es': 'Espacio de clientes', 'pt': 'Espaco de clientes'},
    'Add Client': {'es': 'Agregar cliente', 'pt': 'Adicionar cliente'},
    'Add to Calendar': {'es': 'Agregar al calendario', 'pt': 'Adicionar ao calendario'},
    'New Estimate': {'es': 'Nuevo presupuesto', 'pt': 'Novo orcamento'},
    'New Invoice': {'es': 'Nueva factura', 'pt': 'Nova fatura'},
    'Send Receipt': {'es': 'Enviar recibo', 'pt': 'Enviar recibo'},
    'Delete Permanently': {'es': 'Eliminar permanentemente', 'pt': 'Excluir permanentemente'},
    'Client Actions': {'es': 'Acciones del cliente', 'pt': 'Acoes do cliente'},
    'Jump directly from a saved client into scheduling, estimates, invoices, and receipts.': {
        'es': 'Salta directamente desde un cliente guardado a agenda, presupuestos, facturas y recibos.',
        'pt': 'Vá direto de um cliente salvo para agenda, orcamentos, faturas e recibos.',
    },
    'Linked records': {'es': 'Registros vinculados', 'pt': 'Registros vinculados'},
    'Delete permanently only after linked sales and schedule records are cleared.': {
        'es': 'Elimina permanentemente solo despues de limpiar los registros de ventas y agenda vinculados.',
        'pt': 'Exclua permanentemente somente depois de limpar os registros vinculados de vendas e agenda.',
    },
    'This client has linked invoices, estimates, jobs, or schedule entries and cannot be permanently deleted yet.': {
        'es': 'Este cliente tiene facturas, presupuestos, trabajos o agendas vinculadas y aun no puede eliminarse permanentemente.',
        'pt': 'Este cliente possui faturas, orcamentos, servicos ou agendas vinculadas e ainda nao pode ser excluido permanentemente.',
    },
    'Send a payment receipt after the invoice is marked paid.': {
        'es': 'Envia un recibo de pago despues de marcar la factura como pagada.',
        'pt': 'Envie um recibo de pagamento depois que a fatura for marcada como paga.',
    },
    'Informational tool only': {'es': 'Herramienta solo informativa', 'pt': 'Ferramenta apenas informativa'},
    'LedgerFlow provides organization, summaries, and workflow tools. It does not provide financial, tax, legal, or accounting advice and does not replace a licensed professional.': {
        'es': 'LedgerFlow ofrece organizacion, resumos y herramientas de flujo. No brinda asesoramiento financiero, fiscal, legal ni contable y no reemplaza a un profesional licenciado.',
        'pt': 'A LedgerFlow oferece organizacao, resumos e ferramentas de fluxo. Nao fornece orientacao financeira, fiscal, juridica ou contabil e nao substitui um profissional licenciado.',
    },
    'Operational LedgerFlow gives service businesses a focused command center for jobs, dispatch, scheduling, team coordination, and field execution.': {
        'es': 'Operational LedgerFlow ofrece a las empresas de servicios un centro de control enfocado para trabajos, despacho, agenda, coordinacion del equipo y ejecucion en campo.',
        'pt': 'A LedgerFlow Operacional oferece aos negocios de servicos um centro de comando focado em servicos, despacho, agenda, coordenacao da equipe e execucao em campo.',
    },
    'Secure administrator and business access for the operational workspace.': {
        'es': 'Acceso seguro para administradores y empresas al espacio operativo.',
        'pt': 'Acesso seguro para administradores e empresas ao espaco operacional.',
    },
    'Operational LedgerFlow is the operations product in the LedgerFlow family, built for daily service-business execution.': {
        'es': 'Operational LedgerFlow es el producto de operaciones de la familia LedgerFlow, creado para la ejecucion diaria de empresas de servicios.',
        'pt': 'A LedgerFlow Operacional e o produto de operacoes da familia LedgerFlow, criado para a execucao diaria de negocios de servicos.',
    },
    'Private invited-client rollout. Core portal functions are live and actively administered while final improvements continue.': {
        'es': 'Lanzamiento privado para clientes invitados. Las funciones principales ya estan activas y siguen bajo administracion directa mientras continuan los ajustes finales.',
        'pt': 'Lancamento privado para clientes convidados. As funcoes principais ja estao ativas e seguem sob administracao direta enquanto os ajustes finais continuam.',
    },
    'Rollout Notice': {'es': 'Aviso de despliegue', 'pt': 'Aviso de lancamento'},
    'Privacy Notice': {'es': 'Aviso de privacidad', 'pt': 'Aviso de privacidade'},
    'Terms of Use': {'es': 'Terminos de uso', 'pt': 'Termos de uso'},
    'Security & Data': {'es': 'Seguridad y datos', 'pt': 'Seguranca e dados'},
    'Main Portal': {'es': 'Portal principal', 'pt': 'Portal principal'},
    'Business': {'es': 'Negocio', 'pt': 'Empresa'},
    'Welcome Business': {'es': 'Bienvenido negocio', 'pt': 'Bem-vindo empresa'},
    'Print Dashboard': {'es': 'Imprimir panel', 'pt': 'Imprimir painel'},
    'Subscription Billing': {'es': 'Facturacion de suscripcion', 'pt': 'Cobranca de assinatura'},
    'Open Billing': {'es': 'Abrir facturacion', 'pt': 'Abrir faturamento'},
    'Plan': {'es': 'Plan', 'pt': 'Plano'},
    'Status': {'es': 'Estado', 'pt': 'Status'},
    'Monthly Fee': {'es': 'Cuota mensual', 'pt': 'Taxa mensal'},
    'Next Billing Date': {'es': 'Proxima fecha de cobro', 'pt': 'Proxima data de cobranca'},
    'Not set': {'es': 'No definido', 'pt': 'Nao definido'},
    'No method recorded yet': {'es': 'Sin metodo registrado', 'pt': 'Nenhum metodo registrado'},
    'Method on file': {'es': 'Metodo registrado', 'pt': 'Metodo registrado'},
    'Administrator Fee Notice': {'es': 'Aviso de cargo del administrador', 'pt': 'Aviso de taxa do administrador'},
    'Review Fees': {'es': 'Revisar cargos', 'pt': 'Revisar taxas'},
    'Income Snapshot': {'es': 'Resumen de ingresos', 'pt': 'Resumo de receitas'},
    'income records saved': {'es': 'registros de ingresos guardados', 'pt': 'registros de receita salvos'},
    'Expenses': {'es': 'Gastos', 'pt': 'Despesas'},
    'Tax Foundation': {'es': 'Base fiscal', 'pt': 'Base fiscal'},
    'Operating Profit': {'es': 'Ganancia operativa', 'pt': 'Lucro operacional'},
    'Adjusted Profit': {'es': 'Ganancia ajustada', 'pt': 'Lucro ajustado'},
    'SE Tax': {'es': 'Impuesto SE', 'pt': 'Imposto autonomo'},
    'Total Est.': {'es': 'Total estimado', 'pt': 'Total estimado'},
    'Mileage Deduction': {'es': 'Deduccion por millaje', 'pt': 'Deducao de quilometragem'},
    'Miles': {'es': 'Millas', 'pt': 'Milhas'},
    'Deduction': {'es': 'Deduccion', 'pt': 'Deducao'},
    'Recent Income Records': {'es': 'Registros recientes de ingresos', 'pt': 'Registros recentes de receita'},
    'Add Income Record': {'es': 'Agregar ingreso', 'pt': 'Adicionar receita'},
    'Job #': {'es': 'Trabajo #', 'pt': 'Servico #'},
    'Date': {'es': 'Fecha', 'pt': 'Data'},
    'Customer': {'es': 'Cliente', 'pt': 'Cliente'},
    'Amount': {'es': 'Monto', 'pt': 'Valor'},
    'Type': {'es': 'Tipo', 'pt': 'Tipo'},
    'Forms': {'es': 'Formularios', 'pt': 'Formularios'},
    'Manage Team Members': {'es': 'Administrar equipo', 'pt': 'Gerenciar equipe'},
    'Pending Administrator Review': {'es': 'Revision pendiente del administrador', 'pt': 'Revisao pendente do administrador'},
    'Approved': {'es': 'Aprobado', 'pt': 'Aprovado'},
    'Needs Correction': {'es': 'Necesita correccion', 'pt': 'Precisa de correcao'},
    'Submit your updates to Administrator for review.': {'es': 'Envia tus cambios al administrador para revision.', 'pt': 'Envie suas atualizacoes ao administrador para revisao.'},
    'Administrator workspace view.': {'es': 'Vista del espacio del administrador.', 'pt': 'Visao do espaco do administrador.'},
    'Note to Administrator (optional)': {'es': 'Nota al administrador (opcional)', 'pt': 'Nota ao administrador (opcional)'},
    'Optional message for Administrator': {'es': 'Mensaje opcional para el administrador', 'pt': 'Mensagem opcional para o administrador'},
    'Submit for Administrator Review': {'es': 'Enviar para revision del administrador', 'pt': 'Enviar para revisao do administrador'},
    'Business welcome': {'es': 'Bienvenida del negocio', 'pt': 'Boas-vindas da empresa'},
    'Owner and user details': {'es': 'Detalles del propietario y usuario', 'pt': 'Detalhes do proprietario e usuario'},
    'How-to video space': {'es': 'Espacio para videos', 'pt': 'Espaco para videos'},
    'Quick first steps': {'es': 'Primeros pasos', 'pt': 'Primeiros passos'},
    'Health coverage options': {'es': 'Opciones de salud', 'pt': 'Opcoes de saude'},
    'Tax-favored benefit accounts': {'es': 'Cuentas con ventaja fiscal', 'pt': 'Contas com vantagem fiscal'},
    'Retirement plan choices': {'es': 'Opciones de retiro', 'pt': 'Opcoes de aposentadoria'},
    'Federal obligations and notices': {'es': 'Obligaciones y avisos federales', 'pt': 'Obrigacoes e avisos federais'},
    'Welcome page': {'es': 'Pagina de bienvenida', 'pt': 'Pagina de boas-vindas'},
    'Business onboarding support': {'es': 'Apoyo de incorporacion', 'pt': 'Apoio de onboarding'},
    'Canva video ready': {'es': 'Listo para video Canva', 'pt': 'Pronto para video Canva'},
    'Welcome to LedgerFlow': {'es': 'Bienvenido a LedgerFlow', 'pt': 'Bem-vindo a LedgerFlow'},
    'A guided landing page for this business with clear first steps, personalized details, and a future-ready training area for how-to videos.': {'es': 'Una pagina guiada para este negocio con primeros pasos claros, detalles personalizados y un area futura para videos de ayuda.', 'pt': 'Uma pagina guiada para esta empresa com primeiros passos claros, detalhes personalizados e uma area futura para videos de ajuda.'},
    'Open Dashboard': {'es': 'Abrir panel', 'pt': 'Abrir painel'},
    'Your LedgerFlow workspace business profile': {'es': 'Perfil del negocio en LedgerFlow', 'pt': 'Perfil da empresa no LedgerFlow'},
    'User Name': {'es': 'Nombre del usuario', 'pt': 'Nome do usuario'},
    'The signed-in user for this session': {'es': 'Usuario conectado en esta sesion', 'pt': 'Usuario conectado nesta sessao'},
    'Owner Name': {'es': 'Nombre del propietario', 'pt': 'Nome do proprietario'},
    'Primary business contact / owner record': {'es': 'Contacto principal / registro del propietario', 'pt': 'Contato principal / registro do proprietario'},
    'Workspace Ready': {'es': 'Espacio listo', 'pt': 'Espaco pronto'},
    'Income records, billing, calendar, and operational tools are ready.': {'es': 'Registros, facturacion, calendario y herramientas operativas estan listos.', 'pt': 'Registros, faturamento, calendario e ferramentas operacionais estao prontos.'},
    'Welcome Message': {'es': 'Mensaje de bienvenida', 'pt': 'Mensagem de boas-vindas'},
    'Personalized': {'es': 'Personalizado', 'pt': 'Personalizado'},
    'Recommended First Steps': {'es': 'Primeros pasos recomendados', 'pt': 'Primeiros passos recomendados'},
    'Start Here': {'es': 'Empieza aqui', 'pt': 'Comece aqui'},
    'How-To Videos': {'es': 'Videos de ayuda', 'pt': 'Videos de ajuda'},
    'These training slots are ready for future Canva videos. Keep each video polished, calm, and task-focused so the Welcome Center feels like a premium onboarding experience.': {'es': 'Estos espacios estan listos para futuros videos de Canva. Mantenga cada video claro, tranquilo y enfocado en tareas.', 'pt': 'Esses espacos estao prontos para futuros videos do Canva. Mantenha cada video claro, calmo e focado em tarefas.'},
    'Video Placeholder': {'es': 'Espacio de video', 'pt': 'Espaco de video'},
    'Workspace Snapshot': {'es': 'Resumen del espacio', 'pt': 'Resumo do espaco'},
    'Quick View': {'es': 'Vista rapida', 'pt': 'Visao rapida'},
    'Saved income records in this workspace': {'es': 'Registros guardados en este espacio', 'pt': 'Registros salvos neste espaco'},
    'Gross Income': {'es': 'Ingreso bruto', 'pt': 'Receita bruta'},
    'Current total based on saved records': {'es': 'Total actual segun registros guardados', 'pt': 'Total atual com base nos registros salvos'},
    'Estimated Operating Profit': {'es': 'Ganancia operativa estimada', 'pt': 'Lucro operacional estimado'},
    'A quick high-level view of current business performance': {'es': 'Una vista rapida del rendimiento actual del negocio', 'pt': 'Uma visao rapida do desempenho atual da empresa'},
    'Business guide': {'es': 'Guia del negocio', 'pt': 'Guia da empresa'},
    'Official links only': {'es': 'Solo enlaces oficiales', 'pt': 'Somente links oficiais'},
    'Federal overview': {'es': 'Resumen federal', 'pt': 'Visao federal'},
    'A practical business-owner guide to tax-favored benefit opportunities, federal employer obligations, and live official resources you can trust.': {'es': 'Una guia practica para oportunidades de beneficios, obligaciones federales y recursos oficiales confiables.', 'pt': 'Um guia pratico para oportunidades de beneficios, obrigacoes federais e recursos oficiais confiaveis.'},
    'Back to Overview': {'es': 'Volver al resumen', 'pt': 'Voltar a visao geral'},
    'Benefit Opportunities': {'es': 'Oportunidades de beneficios', 'pt': 'Oportunidades de beneficios'},
    'Focused on health, retirement, and tax-favored benefit design.': {'es': 'Enfocado en salud, retiro y beneficios con ventaja fiscal.', 'pt': 'Focado em saude, aposentadoria e beneficios com vantagem fiscal.'},
    'Federal Checkpoints': {'es': 'Puntos federales', 'pt': 'Pontos federais'},
    'Use these before changing coverage, notices, or employer policy.': {'es': 'Usa esto antes de cambiar cobertura, avisos o politicas.', 'pt': 'Use isto antes de mudar cobertura, avisos ou politicas.'},
    'Official Resources': {'es': 'Recursos oficiales', 'pt': 'Recursos oficiais'},
    'IRS, DOL, EBSA, and HealthCare.gov links only.': {'es': 'Solo enlaces del IRS, DOL, EBSA y HealthCare.gov.', 'pt': 'Somente links do IRS, DOL, EBSA e HealthCare.gov.'},
    'Important Note': {'es': 'Nota importante', 'pt': 'Nota importante'},
    'Size Matters': {'es': 'El tamano importa', 'pt': 'O tamanho importa'},
    'Many rules depend on workforce size, plan type, and state law.': {'es': 'Muchas reglas dependen del tamano del equipo, el plan y la ley estatal.', 'pt': 'Muitas regras dependem do tamanho da equipe, do plano e da lei estadual.'},
    'How to Use This Page': {'es': 'Como usar esta pagina', 'pt': 'Como usar esta pagina'},
    'Practical': {'es': 'Practico', 'pt': 'Pratico'},
    'Opportunity Lane': {'es': 'Linea de oportunidad', 'pt': 'Faixa de oportunidade'},
    'Ways benefits may help the business': {'es': 'Como los beneficios pueden ayudar al negocio', 'pt': 'Como os beneficios podem ajudar a empresa'},
    'Compliance Lane': {'es': 'Linea de cumplimiento', 'pt': 'Faixa de conformidade'},
    'What to review before you offer benefits': {'es': 'Que revisar antes de ofrecer beneficios', 'pt': 'O que revisar antes de oferecer beneficios'},
    'Official Resource Library': {'es': 'Biblioteca oficial de recursos', 'pt': 'Biblioteca oficial de recursos'},
    'Live Links': {'es': 'Enlaces en vivo', 'pt': 'Links ativos'},
    'Billing Workspace': {'es': 'Espacio de facturacion', 'pt': 'Espaco de faturamento'},
    'Billing Center': {'es': 'Centro de facturacion', 'pt': 'Centro de faturamento'},
    'Subscription + Administrator Fees': {'es': 'Suscripcion + cargos del administrador', 'pt': 'Assinatura + taxas do administrador'},
    'Recurring monthly service': {'es': 'Servicio mensual recurrente', 'pt': 'Servico mensal recorrente'},
    'Subscription Status': {'es': 'Estado de suscripcion', 'pt': 'Status da assinatura'},
    'Next billing': {'es': 'Proximo cobro', 'pt': 'Proxima cobranca'},
    'not scheduled': {'es': 'sin programar', 'pt': 'nao agendado'},
    'No default method on file': {'es': 'Sin metodo predeterminado', 'pt': 'Sem metodo padrao'},
    'Recurring subscription tracked separately': {'es': 'Suscripcion recurrente separada', 'pt': 'Assinatura recorrente separada'},
    'One-time administrator fees tracked separately': {'es': 'Cargos unicos separados', 'pt': 'Taxas unicas separadas'},
    'Action Needed': {'es': 'Accion necesaria', 'pt': 'Acao necessaria'},
    'Review Administrator Fees': {'es': 'Revisar cargos del administrador', 'pt': 'Revisar taxas do administrador'},
    'Manage Method On File': {'es': 'Administrar metodo registrado', 'pt': 'Gerenciar metodo salvo'},
    'Recurring Service': {'es': 'Servicio recurrente', 'pt': 'Servico recorrente'},
    'One-Time Charges': {'es': 'Cargos unicos', 'pt': 'Cobrancas unicas'},
    'Open Fees': {'es': 'Cargos abiertos', 'pt': 'Taxas em aberto'},
    'Fee History': {'es': 'Historial de cargos', 'pt': 'Historico de taxas'},
    'Amount Due': {'es': 'Monto adeudado', 'pt': 'Valor devido'},
    'Description': {'es': 'Descripcion', 'pt': 'Descricao'},
    'Due Date': {'es': 'Fecha de vencimiento', 'pt': 'Data de vencimento'},
    'Collection Method': {'es': 'Metodo de cobro', 'pt': 'Metodo de cobranca'},
    'Next Step': {'es': 'Siguiente paso', 'pt': 'Proximo passo'},
    'Trust & Policies': {'es': 'Confianza y politicas', 'pt': 'Confianca e politicas'},
    'Private Client Rollout Notice': {'es': 'Aviso de lanzamiento privado', 'pt': 'Aviso de lancamento privado'},
    'Core LedgerFlow client functions are live for invited clients while final platform refinements continue under administrator oversight.': {'es': 'Las funciones centrales ya estan activas para clientes invitados mientras continuan los ajustes finales.', 'pt': 'As funcoes centrais ja estao ativas para clientes convidados enquanto os ajustes finais continuam.'},
    'Final Rollout Notice': {'es': 'Aviso final de despliegue', 'pt': 'Aviso final de lancamento'},
    'Live Now': {'es': 'Activo ahora', 'pt': 'Ativo agora'},
    'Client Data': {'es': 'Datos del cliente', 'pt': 'Dados do cliente'},
    'Portal Use': {'es': 'Uso del portal', 'pt': 'Uso do portal'},
    'Important': {'es': 'Importante', 'pt': 'Importante'},
})

TRANSLATIONS.update({
    'Private client portal currently in final invited-client rollout. Core workspace functions are live, permission-based, and may continue to improve as the platform is finalized.': {
        'es': 'Este portal privado para clientes esta en lanzamiento final para invitados. Las funciones centrales estan activas, con acceso por permisos, y pueden seguir mejorando mientras se finaliza la plataforma.',
        'pt': 'Este portal privado para clientes esta em lancamento final para convidados. As funcoes centrais estao ativas, com acesso por permissao, e podem continuar melhorando enquanto a plataforma e finalizada.',
    },
    'This portal uses secured account controls and active administrator oversight. It does not claim formal security certification or guarantee uninterrupted service.': {
        'es': 'Este portal usa controles de cuenta protegidos y supervision activa del administrador. No declara certificacion formal ni garantiza servicio ininterrumpido.',
        'pt': 'Este portal usa controles de conta protegidos e supervisao ativa do administrador. Nao declara certificacao formal nem garante servico ininterrupto.',
    },
    'You are viewing a single business workspace. Use one of these to return to admin mode.': {
        'es': 'Estas viendo un solo espacio empresarial. Usa una de estas opciones para volver al modo administrador.',
        'pt': 'Voce esta vendo um unico espaco empresarial. Use uma destas opcoes para voltar ao modo administrador.',
    },
    'Open Billing Setup': {'es': 'Abrir configuracion de facturacion', 'pt': 'Abrir configuracao de faturamento'},
    'Return to Administrator Dashboard': {'es': 'Volver al panel del administrador', 'pt': 'Voltar ao painel do administrador'},
    'Financial control, billing visibility, payroll context, and day-to-day business performance in one executive workspace.': {
        'es': 'Control financiero, visibilidad de facturacion, contexto de nomina y rendimiento diario del negocio en un solo espacio ejecutivo.',
        'pt': 'Controle financeiro, visibilidade de faturamento, contexto de folha e desempenho diario da empresa em um unico espaco executivo.',
    },
    'Open Billing to manage the subscription method on file and any one-time administrator fees.': {
        'es': 'Abre Facturacion para administrar el metodo registrado y cualquier cargo unico del administrador.',
        'pt': 'Abra Faturamento para administrar o metodo salvo e quaisquer taxas unicas do administrador.',
    },
    'across': {'es': 'en', 'pt': 'em'},
    'open fee items': {'es': 'cargos abiertos', 'pt': 'taxas em aberto'},
    'This stays separate from your day-to-day customer payment activity.': {
        'es': 'Esto se mantiene separado de tu actividad normal de cobro a clientes.',
        'pt': 'Isto permanece separado da sua atividade normal de cobranca de clientes.',
    },
    'Administrator Review Status': {'es': 'Estado de revision del administrador', 'pt': 'Status de revisao do administrador'},
    'Open Welcome': {'es': 'Abrir bienvenida', 'pt': 'Abrir boas-vindas'},
    'A guided welcome space for this business with owner details, first-step direction, and future how-to video slots for Canva training content.': {
        'es': 'Un espacio guiado de bienvenida para este negocio con datos del propietario, orientacion inicial y espacios futuros para videos de capacitacion en Canva.',
        'pt': 'Um espaco guiado de boas-vindas para esta empresa com dados do proprietario, orientacao inicial e espacos futuros para videos de treinamento no Canva.',
    },
    'Open Guide': {'es': 'Abrir guia', 'pt': 'Abrir guia'},
    'Review tax-favored benefit options, employer obligations, and official federal resources before changing health, retirement, or leave offerings.': {
        'es': 'Revisa opciones de beneficios con ventaja fiscal, obligaciones del empleador y recursos federales oficiales antes de cambiar salud, retiro o licencias.',
        'pt': 'Revise opcoes de beneficios com vantagem fiscal, obrigacoes do empregador e recursos federais oficiais antes de mudar saude, aposentadoria ou licencas.',
    },
    'Anything your administrator should know about billing or contact preferences': {
        'es': 'Cualquier detalle que tu administrador deba saber sobre facturacion o preferencias de contacto',
        'pt': 'Qualquer detalhe que seu administrador deva saber sobre faturamento ou preferencias de contato',
    },
    'Coming Soon:': {'es': 'Proximamente:', 'pt': 'Em breve:'},
    'Assigned automatically from your selected tier': {'es': 'Asignado automaticamente segun tu plan', 'pt': 'Atribuido automaticamente com base no seu plano'},
    'Suggested monthly platform fee for your selected tier': {'es': 'Cuota mensual sugerida para tu plan', 'pt': 'Valor mensal sugerido para o seu plano'},
    'This becomes your first recorded billing date': {'es': 'Esta sera tu primera fecha registrada de cobro', 'pt': 'Esta sera sua primeira data registrada de cobranca'},
    'This private client rollout uses administrator-managed billing. Your selected plan, pricing, and method on file are saved now so billing can begin immediately, while self-service autopay and premium banking tools continue through final buildout.': {
        'es': 'Este lanzamiento privado usa facturacion administrada. Tu plan, precio y metodo registrado se guardan ahora para que el cobro pueda comenzar de inmediato, mientras el autopago y las herramientas bancarias premium siguen en desarrollo final.',
        'pt': 'Este lancamento privado usa faturamento administrado. Seu plano, preco e metodo salvo sao guardados agora para que a cobranca possa comecar imediatamente, enquanto o autopagamento e as ferramentas bancarias premium seguem em desenvolvimento final.',
    },
    'Add the payment method your business wants on file for subscription billing. This creates or updates your default billing method.': {
        'es': 'Agrega el metodo de pago que tu negocio quiere dejar registrado para la suscripcion. Esto crea o actualiza tu metodo predeterminado.',
        'pt': 'Adicione o metodo de pagamento que sua empresa quer manter salvo para a assinatura. Isso cria ou atualiza o metodo padrao.',
    },
    'Method Type': {'es': 'Tipo de metodo', 'pt': 'Tipo de metodo'},
    'Method Label': {'es': 'Etiqueta del metodo', 'pt': 'Etiqueta do metodo'},
    'Primary business card or Operating ACH': {'es': 'Tarjeta principal del negocio o ACH operativo', 'pt': 'Cartao principal da empresa ou ACH operacional'},
    'Card Brand / Bank Name': {'es': 'Marca de tarjeta / banco', 'pt': 'Bandeira do cartao / banco'},
    'Visa or Chase Business Checking': {'es': 'Visa o cuenta comercial Chase', 'pt': 'Visa ou conta comercial Chase'},
    'Account Holder Name': {'es': 'Nombre del titular', 'pt': 'Nome do titular'},
    'Business legal name': {'es': 'Nombre legal del negocio', 'pt': 'Nome legal da empresa'},
    'Last 4 Digits': {'es': 'Ultimos 4 digitos', 'pt': 'Ultimos 4 digitos'},
    'Expiration (MM/YY)': {'es': 'Vencimiento (MM/AA)', 'pt': 'Validade (MM/AA)'},
    'Account Type': {'es': 'Tipo de cuenta', 'pt': 'Tipo de conta'},
    'Checking': {'es': 'Corriente', 'pt': 'Corrente'},
    'Savings': {'es': 'Ahorros', 'pt': 'Poupanca'},
    'Routing Number': {'es': 'Numero de ruta', 'pt': 'Numero de roteamento'},
    'Leave blank to keep current': {'es': 'Deja en blanco para conservar el actual', 'pt': 'Deixe em branco para manter o atual'},
    '9 digits': {'es': '9 digitos', 'pt': '9 digitos'},
    'Account Number': {'es': 'Numero de cuenta', 'pt': 'Numero da conta'},
    'Enter account number': {'es': 'Ingresa el numero de cuenta', 'pt': 'Digite o numero da conta'},
    'Confirm Account Number': {'es': 'Confirmar numero de cuenta', 'pt': 'Confirmar numero da conta'},
    'Re-enter account number': {'es': 'Vuelve a ingresar el numero de cuenta', 'pt': 'Digite novamente o numero da conta'},
    'Note (optional)': {'es': 'Nota (opcional)', 'pt': 'Nota (opcional)'},
    'Optional billing contact or setup note': {'es': 'Nota opcional de facturacion o configuracion', 'pt': 'Nota opcional de faturamento ou configuracao'},
    'When you complete this step, LedgerFlow will save your business profile, activate your subscription record, save your method on file, and unlock your full business workspace.': {
        'es': 'Al completar este paso, LedgerFlow guardara el perfil del negocio, activara la suscripcion, guardara el metodo registrado y desbloqueara el espacio completo.',
        'pt': 'Ao concluir esta etapa, o LedgerFlow salvara o perfil da empresa, ativara a assinatura, salvara o metodo registrado e liberara o espaco completo.',
    },
    'welcome to LedgerFlow.': {'es': 'bienvenido a LedgerFlow.', 'pt': 'bem-vindo ao LedgerFlow.'},
    'Your workspace for': {'es': 'Tu espacio para', 'pt': 'Seu espaco para'},
    'is designed to keep billing, income records, team operations, payroll context, planning, and business coordination organized in one place.': {
        'es': 'esta pensado para mantener facturacion, ingresos, equipo, contexto de nomina, planificacion y coordinacion del negocio organizados en un solo lugar.',
        'pt': 'foi pensado para manter faturamento, receitas, equipe, contexto de folha, planejamento e coordenacao da empresa organizados em um so lugar.',
    },
    'Use this Welcome Center as your calm starting point. From here, you can move into the dashboard, review billing, track income, manage team members, and later watch guided how-to videos built specifically for this software.': {
        'es': 'Usa este Centro de Bienvenida como tu punto de inicio. Desde aqui puedes entrar al panel, revisar facturacion, registrar ingresos, administrar el equipo y luego ver videos guiados creados para este software.',
        'pt': 'Use esta Central de Boas-vindas como seu ponto de partida. Daqui voce pode entrar no painel, revisar faturamento, registrar receitas, administrar a equipe e depois ver videos guiados criados para este software.',
    },
    'Review Billing': {'es': 'Revisar facturacion', 'pt': 'Revisar faturamento'},
    'Save Income Records': {'es': 'Guardar ingresos', 'pt': 'Salvar receitas'},
    'Subscription billing, method on file, and one-time administrator fees in one calm premium billing workspace.': {
        'es': 'Facturacion de suscripcion, metodo registrado y cargos unicos del administrador en un solo espacio de cobro.',
        'pt': 'Faturamento de assinatura, metodo salvo e taxas unicas do administrador em um unico espaco de cobranca.',
    },
    'Back to Administrator': {'es': 'Volver al administrador', 'pt': 'Voltar ao administrador'},
    'Subscription Plan': {'es': 'Plan de suscripcion', 'pt': 'Plano de assinatura'},
    'This live portal is billed as a private administrator-managed client service. Your selected plan and method on file are active now, while fully automated self-checkout and premium banking tools continue through final rollout.': {
        'es': 'Este portal en vivo se cobra como un servicio privado administrado. Tu plan y metodo registrado ya estan activos, mientras el autoservicio y las herramientas bancarias premium continúan en desarrollo final.',
        'pt': 'Este portal ao vivo e cobrado como um servico privado administrado. Seu plano e metodo salvo ja estao ativos, enquanto o autoatendimento e as ferramentas bancarias premium continuam em desenvolvimento final.',
    },
    'Use one default payment method for subscription billing and optionally keep one backup on file. Full card storage and live autopay are not running inside this app.': {
        'es': 'Usa un metodo predeterminado para la suscripcion y opcionalmente uno de respaldo. El almacenamiento completo de tarjetas y el autopago aun no corren dentro de esta app.',
        'pt': 'Use um metodo padrao para a assinatura e opcionalmente um de backup. O armazenamento completo de cartoes e o autopagamento ainda nao rodam dentro deste app.',
    },
    'Update Method On File': {'es': 'Actualizar metodo registrado', 'pt': 'Atualizar metodo salvo'},
    'Open administrator fees awaiting action': {'es': 'Cargos del administrador pendientes de accion', 'pt': 'Taxas do administrador aguardando acao'},
    'Pending or processing items': {'es': 'Elementos pendientes o en proceso', 'pt': 'Itens pendentes ou em processamento'},
    'Previously completed administrator fees': {'es': 'Cargos del administrador completados anteriormente', 'pt': 'Taxas do administrador concluidas anteriormente'},
    'Team Member Portal Access': {'es': 'Acceso al portal del equipo', 'pt': 'Acesso ao portal da equipe'},
    'your work, pay, notices, and manager messages stay available in one clean portal menu.': {
        'es': 'tu trabajo, pagos, avisos y mensajes del administrador quedan disponibles en un solo menu claro.',
        'pt': 'seu trabalho, pagamentos, avisos e mensagens do administrador ficam disponiveis em um unico menu claro.',
    },
})

TRANSLATIONS.update({
    'Active Business': {'es': 'Empresa activa', 'pt': 'Empresa ativa'},
    'Supervise one business at a time without losing the operational view.': {
        'es': 'Supervisa una empresa por vez sin perder la vista operativa.',
        'pt': 'Supervisione uma empresa por vez sem perder a visao operacional.',
    },
    'Jobs, dispatch, scheduling, team coordination, and operational visibility in one focused workspace.': {
        'es': 'Trabajos, despacho, agenda, coordinacion del equipo y visibilidad operativa en un solo espacio enfocado.',
        'pt': 'Servicos, despacho, agenda, coordenacao da equipe e visibilidade operacional em um unico espaco focado.',
    },
    'Operations': {'es': 'Operaciones', 'pt': 'Operacoes'},
    'Dashboard': {'es': 'Panel', 'pt': 'Painel'},
    'Jobs': {'es': 'Trabajos', 'pt': 'Servicos'},
    'Dispatch': {'es': 'Despacho', 'pt': 'Despacho'},
    'Team': {'es': 'Equipo', 'pt': 'Equipe'},
    'Availability': {'es': 'Disponibilidad', 'pt': 'Disponibilidade'},
    'Activity': {'es': 'Actividad', 'pt': 'Atividade'},
    'Library': {'es': 'Biblioteca', 'pt': 'Biblioteca'},
    'Locations': {'es': 'Ubicaciones', 'pt': 'Locais'},
    'Templates': {'es': 'Plantillas', 'pt': 'Modelos'},
    'Read-Only Summary': {'es': 'Resumen solo lectura', 'pt': 'Resumo somente leitura'},
    'Admin Exit': {'es': 'Salida del administrador', 'pt': 'Saida do administrador'},
    'Open Admin Controls': {'es': 'Abrir controles del administrador', 'pt': 'Abrir controles do administrador'},
    'Operational LedgerFlow is focused on jobs, dispatch, scheduling, team coordination, and field execution for service businesses.': {
        'es': 'Operational LedgerFlow se enfoca en trabajos, despacho, agenda, coordinacion del equipo y ejecucion en campo para negocios de servicios.',
        'pt': 'A LedgerFlow Operacional foca em servicos, despacho, agenda, coordenacao da equipe e execucao em campo para negocios de servicos.',
    },
    'Operational data stays in the business workspace, administrator supervision remains business-scoped, and the worker portal stays separate and restricted.': {
        'es': 'Los datos operativos permanecen en el espacio empresarial, la supervision del administrador sigue limitada al negocio y el portal del trabajador permanece separado y restringido.',
        'pt': 'Os dados operacionais permanecem no espaco da empresa, a supervisao do administrador continua limitada ao negocio e o portal do trabalhador permanece separado e restrito.',
    },
    'Use Income Records to begin saving business income in a tax-preparation-friendly format.': {
        'es': 'Usa Registros de Ingresos para comenzar a guardar ingresos del negocio en un formato amigable para impuestos.',
        'pt': 'Use Registros de Receita para comecar a salvar receitas da empresa em um formato amigavel para impostos.',
    },
    'Open Team Members if you need to add, update, or organize staff and payout information.': {
        'es': 'Abre Miembros del Equipo si necesitas agregar, actualizar u organizar personal e informacion de pagos.',
        'pt': 'Abra Membros da Equipe se precisar adicionar, atualizar ou organizar funcionarios e informacoes de pagamento.',
    },
    'W-4': {'es': 'W-4', 'pt': 'W-4'},
    'W-2': {'es': 'W-2', 'pt': 'W-2'},
    '1099': {'es': '1099', 'pt': '1099'},
    'These charges are owed by your business to your administrator and are separate from your customer payments.': {
        'es': 'Estos cargos son adeudados por tu negocio a tu administrador y estan separados de tus pagos de clientes.',
        'pt': 'Essas cobrancas sao devidas pela sua empresa ao administrador e ficam separadas dos pagamentos dos seus clientes.',
    },
    'This business is billed on': {'es': 'Este negocio se factura en', 'pt': 'Esta empresa e faturada em'},
    'but the workspace is intentionally unlocked at': {'es': 'pero el espacio esta desbloqueado intencionalmente en', 'pt': 'mas o espaco esta intencionalmente liberado em'},
    'This lets your administrator grant broader tools without changing the subscription price being paid.': {
        'es': 'Esto permite que tu administrador otorgue herramientas mas amplias sin cambiar el precio de la suscripcion pagada.',
        'pt': 'Isso permite que o administrador conceda ferramentas mais amplas sem mudar o preco da assinatura paga.',
    },
    'Override note': {'es': 'Nota de excepcion', 'pt': 'Nota de excecao'},
    'Monthly Subscription': {'es': 'Suscripcion mensual', 'pt': 'Assinatura mensal'},
    'No plan code recorded yet': {'es': 'Aun no hay codigo de plan registrado', 'pt': 'Ainda nao ha codigo de plano registrado'},
    'Default Method': {'es': 'Metodo predeterminado', 'pt': 'Metodo padrao'},
    'Not enrolled yet': {'es': 'Aun no registrado', 'pt': 'Ainda nao registrado'},
    'Automatic Withdrawal': {'es': 'Retiro automatico', 'pt': 'Retirada automatica'},
    'Authorized': {'es': 'Autorizado', 'pt': 'Autorizado'},
    'Manual approval': {'es': 'Aprobacion manual', 'pt': 'Aprovacao manual'},
    'Runs from the default saved method': {'es': 'Se ejecuta desde el metodo predeterminado guardado', 'pt': 'Roda a partir do metodo padrao salvo'},
    'Use this if you want approval before collection': {'es': 'Usa esto si quieres aprobacion antes del cobro', 'pt': 'Use isso se quiser aprovacao antes da cobranca'},
    'Granted Access': {'es': 'Acceso concedido', 'pt': 'Acesso concedido'},
    'Backup Method': {'es': 'Metodo de respaldo', 'pt': 'Metodo de backup'},
    'Optional': {'es': 'Opcional', 'pt': 'Opcional'},
    'Active saved methods': {'es': 'Metodos guardados activos', 'pt': 'Metodos salvos ativos'},
    'Status': {'es': 'Estado', 'pt': 'Status'},
    'Set as default': {'es': 'Definir como predeterminado', 'pt': 'Definir como padrao'},
    'Set as backup': {'es': 'Definir como respaldo', 'pt': 'Definir como backup'},
    'Save Payment Method': {'es': 'Guardar metodo de pago', 'pt': 'Salvar metodo de pagamento'},
    'Review Existing Payment Methods': {'es': 'Revisar metodos de pago existentes', 'pt': 'Revisar metodos de pagamento existentes'},
    'Default': {'es': 'Predeterminado', 'pt': 'Padrao'},
    'Backup': {'es': 'Respaldo', 'pt': 'Backup'},
    'Recorded method:': {'es': 'Metodo registrado:', 'pt': 'Metodo registrado:'},
    'ending in': {'es': 'terminado en', 'pt': 'terminando em'},
    'expires': {'es': 'vence', 'pt': 'vence'},
    'Update Method': {'es': 'Actualizar metodo', 'pt': 'Atualizar metodo'},
    'Remove Method': {'es': 'Eliminar metodo', 'pt': 'Remover metodo'},
    'No payment method has been recorded yet. Add a default card or ACH method so your billing setup is complete.': {
        'es': 'Aun no se ha registrado un metodo de pago. Agrega una tarjeta o ACH predeterminado para completar la configuracion de facturacion.',
        'pt': 'Ainda nao ha metodo de pagamento registrado. Adicione um cartao ou ACH padrao para concluir a configuracao de faturamento.',
    },
    'Administrator fees are one-time charges owed by your business to your administrator. They are separate from your recurring subscription and separate from your own customer payment workflows.': {
        'es': 'Los cargos del administrador son cobros unicos adeudados por tu negocio al administrador. Estan separados de tu suscripcion recurrente y de tus propios flujos de cobro a clientes.',
        'pt': 'As taxas do administrador sao cobrancas unicas devidas pela sua empresa ao administrador. Elas ficam separadas da assinatura recorrente e dos seus proprios fluxos de cobranca de clientes.',
    },
    'No open administrator service fees right now.': {'es': 'No hay cargos abiertos del administrador en este momento.', 'pt': 'Nao ha taxas abertas do administrador neste momento.'},
    'Administrator Fee History': {'es': 'Historico de cargos del administrador', 'pt': 'Historico de taxas do administrador'},
    'Paid': {'es': 'Pagado', 'pt': 'Pago'},
    'Reference': {'es': 'Referencia', 'pt': 'Referencia'},
    'No reference': {'es': 'Sin referencia', 'pt': 'Sem referencia'},
    'No completed administrator fee history yet.': {'es': 'Aun no hay historial de cargos completados del administrador.', 'pt': 'Ainda nao ha historico de taxas concluidas do administrador.'},
    'Subscription + Administrator Fees': {'es': 'Suscripcion + cargos del administrador', 'pt': 'Assinatura + taxas do administrador'},
    'Recurring monthly service': {'es': 'Servicio mensual recurrente', 'pt': 'Servico mensal recorrente'},
    'No default method on file': {'es': 'No hay metodo predeterminado registrado', 'pt': 'Nao ha metodo padrao registrado'},
    'Recurring subscription tracked separately': {'es': 'Suscripcion recurrente seguida por separado', 'pt': 'Assinatura recorrente acompanhada separadamente'},
    'One-time administrator fees tracked separately': {'es': 'Cargos unicos del administrador seguidos por separado', 'pt': 'Taxas unicas do administrador acompanhadas separadamente'},
    'Access override active': {'es': 'Excepcion de acceso activa', 'pt': 'Excecao de acesso ativa'},
    'Review Administrator Fees': {'es': 'Revisar cargos del administrador', 'pt': 'Revisar taxas do administrador'},
    'Manage Method On File': {'es': 'Administrar metodo registrado', 'pt': 'Administrar metodo salvo'},
    'Recurring Service': {'es': 'Servicio recurrente', 'pt': 'Servico recorrente'},
    'Subscription Billing Preferences': {'es': 'Preferencias de cobro de suscripcion', 'pt': 'Preferencias de cobranca da assinatura'},
    'Save Billing Preferences': {'es': 'Guardar preferencias de cobro', 'pt': 'Salvar preferencias de cobranca'},
    'Card': {'es': 'Tarjeta', 'pt': 'Cartao'},
    'ACH / Bank Debit': {'es': 'ACH / Debito bancario', 'pt': 'ACH / Debito bancario'},
    'Manual / Offline': {'es': 'Manual / Offline', 'pt': 'Manual / Offline'},
    'Zelle / Bank Transfer': {'es': 'Zelle / Transferencia bancaria', 'pt': 'Zelle / Transferencia bancaria'},
    'Other': {'es': 'Otro', 'pt': 'Outro'},
    'Needs Update': {'es': 'Necesita actualizacion', 'pt': 'Precisa atualizacao'},
    'Inactive': {'es': 'Inactivo', 'pt': 'Inativo'},
    'Past Due': {'es': 'Vencido', 'pt': 'Vencido'},
    'Paused': {'es': 'Pausado', 'pt': 'Pausado'},
    'Canceled': {'es': 'Cancelado', 'pt': 'Cancelado'},
    'Missing': {'es': 'Faltante', 'pt': 'Ausente'},
    'On File': {'es': 'Registrado', 'pt': 'Registrado'},
    'Pending': {'es': 'Pendiente', 'pt': 'Pendente'},
    'Processing': {'es': 'Procesando', 'pt': 'Processando'},
    'Payment Method': {'es': 'Metodo de pago', 'pt': 'Metodo de pagamento'},
    'Charge Saved Payment Method': {'es': 'Cobrar el metodo guardado', 'pt': 'Cobrar o metodo salvo'},
    'Send Payment Request': {'es': 'Enviar solicitud de pago', 'pt': 'Enviar solicitacao de pagamento'},
    'Send Payment Link / Invoice': {'es': 'Enviar enlace de pago / factura', 'pt': 'Enviar link de pagamento / fatura'},
    'Manual / Offline Payment': {'es': 'Pago manual / offline', 'pt': 'Pagamento manual / offline'},
    'Bank / Zelle Instructions': {'es': 'Instrucciones bancarias / Zelle', 'pt': 'Instrucoes bancarias / Zelle'},
    'Pay Online': {'es': 'Pagar en linea', 'pt': 'Pagar online'},
    'Open the administrator-provided payment page for this one-time fee.': {
        'es': 'Abre la pagina de pago proporcionada por el administrador para este cargo unico.',
        'pt': 'Abra a pagina de pagamento fornecida pelo administrador para esta taxa unica.',
    },
    'Open Payment Link': {'es': 'Abrir enlace de pago', 'pt': 'Abrir link de pagamento'},
    'Charge to Method on File': {'es': 'Cobro al metodo registrado', 'pt': 'Cobrar no metodo salvo'},
    'Your administrator marked this fee to be collected using the saved payment method on file. No self-service payment click is required on your side in this phase.': {
        'es': 'Tu administrador marco este cargo para cobrarse usando el metodo guardado. No se requiere un clic de pago de autoservicio de tu lado en esta fase.',
        'pt': 'Seu administrador marcou esta taxa para ser cobrada usando o metodo salvo. Nenhum clique de pagamento em autoatendimento e necessario do seu lado nesta fase.',
    },
    'Manual Payment': {'es': 'Pago manual', 'pt': 'Pagamento manual'},
    'Follow the manual payment instructions provided by your administrator for this fee.': {
        'es': 'Sigue las instrucciones de pago manual proporcionadas por tu administrador para este cargo.',
        'pt': 'Siga as instrucoes de pagamento manual fornecidas pelo administrador para esta taxa.',
    },
    'Use the Zelle or bank-transfer instructions provided by your administrator for this fee.': {
        'es': 'Usa las instrucciones de Zelle o transferencia bancaria proporcionadas por tu administrador para este cargo.',
        'pt': 'Use as instrucoes de Zelle ou transferencia bancaria fornecidas pelo administrador para esta taxa.',
    },
    'Payment Request Pending': {'es': 'Solicitud de pago pendiente', 'pt': 'Solicitacao de pagamento pendente'},
    'Your administrator will send or complete a payment request for this fee.': {
        'es': 'Tu administrador enviara o completara una solicitud de pago para este cargo.',
        'pt': 'Seu administrador enviara ou concluira uma solicitacao de pagamento para esta taxa.',
    },
    'Open the available payment page for this administrator fee.': {
        'es': 'Abre la pagina de pago disponible para este cargo del administrador.',
        'pt': 'Abra a pagina de pagamento disponivel para esta taxa do administrador.',
    },
    'Payment Details Pending': {'es': 'Detalles de pago pendientes', 'pt': 'Detalhes de pagamento pendentes'},
    'This fee is posted, but your administrator has not added the payment action or instructions yet.': {
        'es': 'Este cargo ya esta publicado, pero tu administrador aun no agrego la accion o instrucciones de pago.',
        'pt': 'Esta taxa ja foi publicada, mas o administrador ainda nao adicionou a acao ou as instrucoes de pagamento.',
    },
    'No open administrator fees right now.': {'es': 'No hay cargos abiertos del administrador en este momento.', 'pt': 'Nao ha taxas abertas do administrador neste momento.'},
    'Your billing center is clear at the moment.': {'es': 'Tu centro de cobro esta despejado en este momento.', 'pt': 'Seu centro de cobranca esta limpo no momento.'},
    'Open administrator fees require review.': {'es': 'Los cargos abiertos del administrador requieren revision.', 'pt': 'As taxas abertas do administrador exigem revisao.'},
    'Review the fee actions below to complete payment.': {'es': 'Revisa las acciones de cobro abajo para completar el pago.', 'pt': 'Revise as acoes de cobranca abaixo para concluir o pagamento.'},
    'This private client portal is active for invited clients and administrator-managed accounts. Core workspace tools are live, and some non-critical experience improvements may continue during the final rollout stage.': {
        'es': 'Este portal privado para clientes esta activo para clientes invitados y cuentas administradas por el administrador. Las herramientas principales ya estan en vivo y algunas mejoras no criticas pueden continuar durante la fase final.',
        'pt': 'Este portal privado para clientes esta ativo para clientes convidados e contas gerenciadas pelo administrador. As ferramentas principais ja estao ao vivo e algumas melhorias nao criticas podem continuar durante a fase final.',
    },
    'Client access is permission-based and controlled by the administrator.': {
        'es': 'El acceso del cliente se basa en permisos y es controlado por el administrador.',
        'pt': 'O acesso do cliente e baseado em permissao e controlado pelo administrador.',
    },
    'Billing, records, schedules, and workspace management functions are active.': {
        'es': 'Las funciones de cobro, registros, agendas y gestion del espacio estan activas.',
        'pt': 'As funcoes de cobranca, registros, agendas e gestao do espaco estao ativas.',
    },
    'Some advanced or premium features may still be labeled coming soon.': {
        'es': 'Algunas funciones avanzadas o premium aun pueden aparecer como proximamente.',
        'pt': 'Alguns recursos avancados ou premium ainda podem aparecer como em breve.',
    },
    'LedgerFlow stores business, team-member, billing, and account-access records needed to operate the portal for invited clients. Information is used to manage the platform, support billing workflows, and maintain administrator-supervised client service.': {
        'es': 'LedgerFlow almacena registros de negocio, equipo, cobro y acceso necesarios para operar el portal para clientes invitados. La informacion se usa para administrar la plataforma, apoyar flujos de cobro y mantener el servicio supervisado por el administrador.',
        'pt': 'O LedgerFlow armazena registros de negocio, equipe, cobranca e acesso necessarios para operar o portal para clientes convidados. As informacoes sao usadas para administrar a plataforma, apoiar fluxos de cobranca e manter o servico supervisionado pelo administrador.',
    },
    'Access is limited to authorized accounts and administrator-managed workflows.': {
        'es': 'El acceso esta limitado a cuentas autorizadas y flujos administrados por el administrador.',
        'pt': 'O acesso e limitado a contas autorizadas e fluxos gerenciados pelo administrador.',
    },
    'Stored information may include contact details, business records, notices, payment-method references, and email-delivery logs.': {
        'es': 'La informacion almacenada puede incluir datos de contacto, registros del negocio, avisos, referencias de metodos de pago y registros de entrega de correos.',
        'pt': 'As informacoes armazenadas podem incluir dados de contato, registros da empresa, avisos, referencias de metodos de pagamento e logs de entrega de e-mails.',
    },
    'Clients should contact their administrator for record corrections, support questions, or account changes.': {
        'es': 'Los clientes deben contactar a su administrador para corregir registros, hacer preguntas de soporte o cambiar la cuenta.',
        'pt': 'Os clientes devem contatar o administrador para corrigir registros, tirar duvidas de suporte ou alterar a conta.',
    },
    'Use of this portal is limited to invited and authorized client accounts. Users must keep login credentials private, use accurate business information, and avoid unauthorized sharing, misuse, or interference with the portal.': {
        'es': 'El uso de este portal esta limitado a cuentas de clientes invitados y autorizados. Los usuarios deben mantener privadas sus credenciales, usar informacion correcta del negocio y evitar compartir sin autorizacion, mal uso o interferencia con el portal.',
        'pt': 'O uso deste portal e limitado a contas de clientes convidados e autorizados. Os usuarios devem manter as credenciais privadas, usar informacoes corretas da empresa e evitar compartilhamento nao autorizado, uso indevido ou interferencia com o portal.',
    },
    'Subscriptions, billing arrangements, and service scope are managed directly through the administrator.': {
        'es': 'Las suscripciones, arreglos de cobro y alcance del servicio se gestionan directamente por medio del administrador.',
        'pt': 'As assinaturas, acordos de cobranca e escopo do servico sao gerenciados diretamente pelo administrador.',
    },
    'Access may be suspended or changed if service is canceled, permissions are removed, or account use becomes improper.': {
        'es': 'El acceso puede suspenderse o cambiarse si el servicio se cancela, se eliminan permisos o el uso de la cuenta se vuelve inapropiado.',
        'pt': 'O acesso pode ser suspenso ou alterado se o servico for cancelado, as permissoes forem removidas ou o uso da conta se tornar inadequado.',
    },
    'The platform may continue to improve through normal updates during final rollout.': {
        'es': 'La plataforma puede seguir mejorando mediante actualizaciones normales durante el lanzamiento final.',
        'pt': 'A plataforma pode continuar melhorando por meio de atualizacoes normais durante o lancamento final.',
    },
    'LedgerFlow uses secured account controls, environment-level application secrets, and administrator-managed access policies. This notice does not represent formal certification, third-party audit attestation, or an absolute guarantee of uninterrupted operation.': {
        'es': 'LedgerFlow usa controles de cuenta protegidos, secretos de aplicacion a nivel de entorno y politicas de acceso administradas. Este aviso no representa certificacion formal, auditoria de terceros ni garantia absoluta de operacion ininterrumpida.',
        'pt': 'O LedgerFlow usa controles de conta protegidos, segredos de aplicacao em nivel de ambiente e politicas de acesso administradas. Este aviso nao representa certificacao formal, auditoria de terceiros nem garantia absoluta de operacao ininterrupta.',
    },
    'Security-sensitive settings are managed through protected administrator controls.': {
        'es': 'Las configuraciones sensibles de seguridad se administran mediante controles protegidos del administrador.',
        'pt': 'As configuracoes sensiveis de seguranca sao gerenciadas por controles protegidos do administrador.',
    },
    'Clients should report suspicious activity immediately to their administrator.': {
        'es': 'Los clientes deben informar actividad sospechosa de inmediato a su administrador.',
        'pt': 'Os clientes devem relatar atividade suspeita imediatamente ao administrador.',
    },
    'Email delivery and billing workflows depend on active third-party service availability.': {
        'es': 'La entrega de correos y los flujos de cobro dependen de la disponibilidad activa de servicios de terceros.',
        'pt': 'A entrega de e-mails e os fluxos de cobranca dependem da disponibilidade ativa de servicos de terceiros.',
    },
    'Business Profiles': {'es': 'Perfiles de negocios', 'pt': 'Perfis de empresas'},
    'Back to Dashboard': {'es': 'Volver al panel', 'pt': 'Voltar ao painel'},
    'Service Level / Pricing Tier': {'es': 'Nivel de servicio / plan de precio', 'pt': 'Nivel de servico / plano de preco'},
    'pricing': {'es': 'precio', 'pt': 'preco'},
    'access': {'es': 'acceso', 'pt': 'acesso'},
    'Subscription:': {'es': 'Suscripcion:', 'pt': 'Assinatura:'},
    'Access override active: billed as': {'es': 'Excepcion de acceso activa: cobrado como', 'pt': 'Excecao de acesso ativa: cobrado como'},
    'granted': {'es': 'concedido', 'pt': 'concedido'},
    'Access granted by administrator:': {'es': 'Acceso concedido por el administrador:', 'pt': 'Acesso concedido pelo administrador:'},
    'Contact missing': {'es': 'Contacto faltante', 'pt': 'Contato ausente'},
    'Kind missing': {'es': 'Tipo faltante', 'pt': 'Tipo ausente'},
    'Address missing': {'es': 'Direccion faltante', 'pt': 'Endereco ausente'},
    'Optional short description like house cleaning or interior painting': {
        'es': 'Descripcion corta opcional como limpieza residencial o pintura interior',
        'pt': 'Descricao curta opcional como limpeza residencial ou pintura interna',
    },
    'Self-Service': {'es': 'Autoservicio', 'pt': 'Autoatendimento'},
    'Match pricing tier': {'es': 'Igualar el plan de precio', 'pt': 'Igualar o plano de preco'},
    'Cleaning': {'es': 'Limpieza', 'pt': 'Limpeza'},
    'Painting': {'es': 'Pintura', 'pt': 'Pintura'},
    'Nails / Beauty': {'es': 'Uñas / Belleza', 'pt': 'Unhas / Beleza'},
    'Massage / Wellness': {'es': 'Masaje / Bienestar', 'pt': 'Massagem / Bem-estar'},
    'Construction': {'es': 'Construccion', 'pt': 'Construcao'},
    'Landscaping': {'es': 'Paisajismo', 'pt': 'Paisagismo'},
    'Floor Installation': {'es': 'Instalacion de pisos', 'pt': 'Instalacao de pisos'},
    'Mobile Detailing': {'es': 'Detallado movil', 'pt': 'Detalhamento movel'},
    'Home Services': {'es': 'Servicios del hogar', 'pt': 'Servicos residenciais'},
    'Childcare': {'es': 'Cuidado infantil', 'pt': 'Cuidado infantil'},
    'Consulting': {'es': 'Consultoria', 'pt': 'Consultoria'},
    'Bookkeeping / Accounting': {'es': 'Contabilidad / Contaduria', 'pt': 'Escrituracao / Contabilidade'},
    'Retail / Boutique': {'es': 'Retail / Boutique', 'pt': 'Varejo / Boutique'},
    'Food / Catering': {'es': 'Comida / Catering', 'pt': 'Comida / Catering'},
    'Fitness / Personal Training': {'es': 'Fitness / Entrenamiento personal', 'pt': 'Fitness / Treinamento pessoal'},
    'LLC': {'es': 'LLC', 'pt': 'LLC'},
    'S-Corp': {'es': 'S-Corp', 'pt': 'S-Corp'},
    'C-Corp': {'es': 'C-Corp', 'pt': 'C-Corp'},
    'Sole Proprietor': {'es': 'Propietario unico', 'pt': 'Empresario individual'},
    'Partnership': {'es': 'Sociedad', 'pt': 'Sociedade'},
    'Nonprofit': {'es': 'Sin fines de lucro', 'pt': 'Sem fins lucrativos'},
    'Private client workspace for owner-led service businesses that need clean billing, records, and calendar visibility.': {
        'es': 'Espacio privado para negocios de servicios dirigidos por el propietario que necesitan cobro limpio, registros y visibilidad de calendario.',
        'pt': 'Espaco privado para negocios de servicos liderados pelo proprietario que precisam de faturamento limpo, registros e visibilidade de calendario.',
    },
    'Best for smaller direct-admin client accounts.': {'es': 'Ideal para cuentas de clientes pequenas con administracion directa.', 'pt': 'Ideal para contas menores com administracao direta.'},
    'Business workspace dashboard': {'es': 'Panel del espacio empresarial', 'pt': 'Painel do espaco empresarial'},
    'Billing center with method on file': {'es': 'Centro de cobro con metodo registrado', 'pt': 'Centro de faturamento com metodo salvo'},
    'Income records and expense tracking': {'es': 'Registros de ingresos y control de gastos', 'pt': 'Registros de receita e controle de despesas'},
    'Calendar and work schedule access': {'es': 'Acceso al calendario y agenda de trabajo', 'pt': 'Acesso ao calendario e agenda de trabalho'},
    'Direct administrator support': {'es': 'Soporte directo del administrador', 'pt': 'Suporte direto do administrador'},
    'Adds team tools and stronger operational support for growing businesses with active payroll coordination.': {
        'es': 'Agrega herramientas de equipo y soporte operativo mas fuerte para negocios en crecimiento con coordinacion activa de nomina.',
        'pt': 'Adiciona ferramentas de equipe e suporte operacional mais forte para negocios em crescimento com coordenacao ativa de folha.',
    },
    'Best for businesses managing staff and payroll visibility.': {'es': 'Ideal para negocios que administran personal y visibilidad de nomina.', 'pt': 'Ideal para empresas que administram equipe e visibilidade de folha.'},
    'Everything in Essential': {'es': 'Todo en Essential', 'pt': 'Tudo no Essential'},
    'Team member portal access': {'es': 'Acceso al portal del equipo', 'pt': 'Acesso ao portal da equipe'},
    'Team member payouts and pay stubs': {'es': 'Pagos del equipo y comprobantes', 'pt': 'Pagamentos da equipe e comprovantes'},
    'Policies, notices, and requests': {'es': 'Politicas, avisos y solicitudes', 'pt': 'Politicas, avisos e solicitacoes'},
    'Expanded administrator guidance': {'es': 'Orientacion ampliada del administrador', 'pt': 'Orientacao ampliada do administrador'},
    'Highest-touch private client tier with premium onboarding, priority support, and principal-level oversight.': {
        'es': 'Nivel privado de mayor acompanamiento con onboarding premium, soporte prioritario y supervision de nivel principal.',
        'pt': 'Nivel privado de maior acompanhamento com onboarding premium, suporte prioritario e supervisao de nivel principal.',
    },
    'Best for clients who want concierge support and deeper administrator involvement.': {'es': 'Ideal para clientes que quieren soporte concierge y una participacion mas profunda del administrador.', 'pt': 'Ideal para clientes que querem suporte concierge e uma participacao mais profunda do administrador.'},
    'Everything in Growth': {'es': 'Todo en Growth', 'pt': 'Tudo no Growth'},
    'Priority support response': {'es': 'Respuesta de soporte prioritaria', 'pt': 'Resposta de suporte prioritaria'},
    'Premium onboarding review': {'es': 'Revision premium de onboarding', 'pt': 'Revisao premium de onboarding'},
    'Principal-level workspace oversight': {'es': 'Supervision del espacio a nivel principal', 'pt': 'Supervisao do espaco em nivel principal'},
    'Higher-touch billing coordination': {'es': 'Coordinacion de cobro de alto acompanamiento', 'pt': 'Coordenacao de cobranca com maior acompanhamento'},
    'Live bank connection': {'es': 'Conexion bancaria en vivo', 'pt': 'Conexao bancaria ao vivo'},
    'Check printing workflow': {'es': 'Flujo de impresion de cheques', 'pt': 'Fluxo de impressao de cheques'},
})

TRANSLATIONS.update({
    'Financial Summary': {'es': 'Resumen financiero', 'pt': 'Resumo financeiro'},
    'Summary Center': {'es': 'Centro de resumen', 'pt': 'Central de resumo'},
    'Income, expenses, mileage, and tax-readiness in one printable reporting view.': {
        'es': 'Ingresos, gastos, kilometraje y preparacion fiscal en una sola vista imprimible.',
        'pt': 'Receitas, despesas, quilometragem e preparo fiscal em uma unica visao imprimivel.',
    },
    'Apply': {'es': 'Aplicar', 'pt': 'Aplicar'},
    'Print Summary': {'es': 'Imprimir resumen', 'pt': 'Imprimir resumo'},
    'Income': {'es': 'Ingresos', 'pt': 'Receitas'},
    'Tax Readiness Snapshot': {'es': 'Resumen de preparacion fiscal', 'pt': 'Resumo de preparacao fiscal'},
    'Quick Print Center': {'es': 'Centro rapido de impresion', 'pt': 'Central rapida de impressao'},
    'Open Report Center': {'es': 'Abrir central de relatorios', 'pt': 'Abrir central de relatorios'},
    'Invoices': {'es': 'Facturas', 'pt': 'Faturas'},
    'Recent Invoices': {'es': 'Facturas recientes', 'pt': 'Faturas recentes'},
    'Recent Mileage': {'es': 'Kilometraje reciente', 'pt': 'Quilometragem recente'},
    'Job #': {'es': 'Trabajo #', 'pt': 'Servico #'},
    'Date': {'es': 'Fecha', 'pt': 'Data'},
    'Customer': {'es': 'Cliente', 'pt': 'Cliente'},
    'Amount': {'es': 'Importe', 'pt': 'Valor'},
    'Purpose': {'es': 'Motivo', 'pt': 'Finalidade'},
    'Miles': {'es': 'Millas', 'pt': 'Milhas'},
    'Deduction': {'es': 'Deduccion', 'pt': 'Deducao'},
    'Invoices:': {'es': 'Facturas:', 'pt': 'Faturas:'},
    'Workers:': {'es': 'Trabajadores:', 'pt': 'Trabalhadores:'},
    'Gas:': {'es': 'Gasolina:', 'pt': 'Combustivel:'},
    'Materials:': {'es': 'Materiales:', 'pt': 'Materiais:'},
    'Adjusted Profit:': {'es': 'Ganancia ajustada:', 'pt': 'Lucro ajustado:'},
    'SE Tax Est.:': {'es': 'Imp. autonomo est.:', 'pt': 'Imp. autonomo est.:'},
    'Total Est.:': {'es': 'Total est.:', 'pt': 'Total est.:'},
    'Report': {'es': 'Reporte', 'pt': 'Relatorio'},
    'Workers': {'es': 'Trabajadores', 'pt': 'Trabalhadores'},
    'Payments': {'es': 'Pagos', 'pt': 'Pagamentos'},
    'All': {'es': 'Todos', 'pt': 'Todos'},
    'Run Report': {'es': 'Generar reporte', 'pt': 'Gerar relatorio'},
    'Print Current Report': {'es': 'Imprimir relatorio atual', 'pt': 'Imprimir relatorio atual'},
    'Print': {'es': 'Imprimir', 'pt': 'Imprimir'},
    'Tax Summary': {'es': 'Resumen fiscal', 'pt': 'Resumo fiscal'},
    'Gross Income': {'es': 'Ingreso bruto', 'pt': 'Receita bruta'},
    'Forms by Worker': {'es': 'Formularios por trabajador', 'pt': 'Formularios por trabalhador'},
    'Worker': {'es': 'Trabajador', 'pt': 'Trabalhador'},
    'Type': {'es': 'Tipo', 'pt': 'Tipo'},
    'Links': {'es': 'Links', 'pt': 'Links'},
    'Filtered by business/date/worker/invoice as selected above': {
        'es': 'Filtrado por negocio/fecha/trabajador/factura segun lo seleccionado arriba',
        'pt': 'Filtrado por empresa/data/trabalhador/fatura conforme selecionado acima',
    },
    'Use Print Current Report for this summary view.': {
        'es': 'Use Imprimir relatorio atual para esta vista de resumen.',
        'pt': 'Use Imprimir relatorio atual para esta visao de resumo.',
    },
    'Name': {'es': 'Nombre', 'pt': 'Nome'},
    'SSN/Tax ID': {'es': 'SSN/ID fiscal', 'pt': 'SSN/ID fiscal'},
    'Hire Date': {'es': 'Fecha de contratacion', 'pt': 'Data de contratacao'},
    'Week': {'es': 'Semana', 'pt': 'Semana'},
    'Description': {'es': 'Descripcion', 'pt': 'Descricao'},
    'From': {'es': 'Desde', 'pt': 'De'},
    'To': {'es': 'Hasta', 'pt': 'Ate'},
    'Client': {'es': 'Cliente', 'pt': 'Cliente'},
    'Clients': {'es': 'Clientes', 'pt': 'Clientes'},
    'Estimates': {'es': 'Presupuestos', 'pt': 'Orcamentos'},
    'Phone': {'es': 'Telefono', 'pt': 'Telefone'},
    'Create Estimate': {'es': 'Crear presupuesto', 'pt': 'Criar orcamento'},
    'Create Invoice': {'es': 'Crear factura', 'pt': 'Criar fatura'},
    'Saved Clients': {'es': 'Clientes guardados', 'pt': 'Clientes salvos'},
    'Open Estimates': {'es': 'Presupuestos abiertos', 'pt': 'Orcamentos abertos'},
    'Approved Estimates': {'es': 'Presupuestos aprobados', 'pt': 'Orcamentos aprovados'},
    'Open Invoices': {'es': 'Facturas abiertas', 'pt': 'Faturas abertas'},
    'Add Saved Client': {'es': 'Agregar cliente guardado', 'pt': 'Adicionar cliente salvo'},
    'Recurring Customers': {'es': 'Clientes recurrentes', 'pt': 'Clientes recorrentes'},
    'Keep repeat customers on file here so estimates and invoices can start faster the next time they come back.': {
        'es': 'Guarda aqui a los clientes recurrentes para que los presupuestos y facturas sean mas rapidos la proxima vez.',
        'pt': 'Mantenha aqui os clientes recorrentes para que orcamentos e faturas comecem mais rapido na proxima vez.',
    },
    'Client Name': {'es': 'Nombre del cliente', 'pt': 'Nome do cliente'},
    'Notes': {'es': 'Notas', 'pt': 'Notas'},
    'Note': {'es': 'Nota', 'pt': 'Nota'},
    'Gate code, preferred contact method, favorite service, or follow-up notes': {
        'es': 'Codigo de acceso, metodo de contacto preferido, servicio favorito o notas de seguimiento',
        'pt': 'Codigo de acesso, metodo de contato preferido, servico favorito ou notas de acompanhamento',
    },
    'Save Client': {'es': 'Guardar cliente', 'pt': 'Salvar cliente'},
    'Recurring Service': {'es': 'Servicio recurrente', 'pt': 'Servico recorrente'},
    'Use this for return clients whose work repeats on a regular schedule.': {
        'es': 'Usa esto para clientes recurrentes cuyo trabajo se repite en un horario regular.',
        'pt': 'Use isto para clientes recorrentes cujo trabalho se repete em uma agenda regular.',
    },
    'One-time / no repeat': {'es': 'Una vez / sin repeticion', 'pt': 'Uma vez / sem repeticao'},
    'Weekly': {'es': 'Semanal', 'pt': 'Semanal'},
    'Every 2 Weeks': {'es': 'Cada 2 semanas', 'pt': 'A cada 2 semanas'},
    'Monthly': {'es': 'Mensual', 'pt': 'Mensal'},
    'Monday': {'es': 'Lunes', 'pt': 'Segunda-feira'},
    'Tuesday': {'es': 'Martes', 'pt': 'Terca-feira'},
    'Wednesday': {'es': 'Miercoles', 'pt': 'Quarta-feira'},
    'Thursday': {'es': 'Jueves', 'pt': 'Quinta-feira'},
    'Friday': {'es': 'Viernes', 'pt': 'Sexta-feira'},
    'Saturday': {'es': 'Sabado', 'pt': 'Sabado'},
    'Sunday': {'es': 'Domingo', 'pt': 'Domingo'},
    'Preferred Service Day': {'es': 'Dia preferido del servicio', 'pt': 'Dia preferido do servico'},
    'Service Start Date': {'es': 'Fecha de inicio del servicio', 'pt': 'Data de inicio do servico'},
    'Service End Date (optional)': {'es': 'Fecha final del servicio (opcional)', 'pt': 'Data final do servico (opcional)'},
    'Default Service Name': {'es': 'Nombre predeterminado del servicio', 'pt': 'Nome padrao do servico'},
    'Default Visit Price': {'es': 'Precio predeterminado por visita', 'pt': 'Preco padrao por visita'},
    'Auto-add upcoming visits to calendar': {'es': 'Agregar automaticamente las proximas visitas al calendario', 'pt': 'Adicionar automaticamente as proximas visitas ao calendario'},
    'Recurring weekly cleaning, biweekly detailing, monthly visit, etc.': {
        'es': 'Limpieza semanal, detallado quincenal, visita mensual, etc.',
        'pt': 'Limpeza semanal, detalhamento quinzenal, visita mensal etc.',
    },
    'Projected recurring revenue': {'es': 'Ingresos recurrentes proyectados', 'pt': 'Receita recorrente projetada'},
    'Upcoming recurring visits': {'es': 'Proximas visitas recurrentes', 'pt': 'Proximas visitas recorrentes'},
    'Next Visit': {'es': 'Proxima visita', 'pt': 'Proxima visita'},
    'Recurrence': {'es': 'Recurrencia', 'pt': 'Recorrencia'},
    'Projected Monthly': {'es': 'Proyectado mensual', 'pt': 'Projetado mensal'},
    'Expected amount': {'es': 'Monto esperado', 'pt': 'Valor esperado'},
    'Open Work Schedule': {'es': 'Abrir agenda de trabajo', 'pt': 'Abrir agenda de trabalho'},
    'No recurring plan': {'es': 'Sin plan recurrente', 'pt': 'Sem plano recorrente'},
    'No upcoming visit generated yet': {'es': 'Aun no se genero ninguna proxima visita', 'pt': 'Ainda nao foi gerada nenhuma proxima visita'},
    'Automatic schedule created': {'es': 'Agenda automatica creada', 'pt': 'Agenda automatica criada'},
    'Generated from recurring client profile.': {'es': 'Generado desde el perfil recurrente del cliente.', 'pt': 'Gerado a partir do perfil recorrente do cliente.'},
    'Create and manage assigned job schedule entries.': {'es': 'Crea y administra trabajos programados.', 'pt': 'Crie e gerencie trabalhos agendados.'},
    'Add Schedule Entry': {'es': 'Agregar entrada de agenda', 'pt': 'Adicionar entrada de agenda'},
    'Assigned Worker(s)': {'es': 'Trabajador(es) asignado(s)', 'pt': 'Trabalhador(es) atribuido(s)'},
    'No workers added yet.': {'es': 'Aun no hay trabajadores agregados.', 'pt': 'Ainda nao ha trabalhadores adicionados.'},
    'Job Address': {'es': 'Direccion del trabajo', 'pt': 'Endereco do servico'},
    'Scope of Work': {'es': 'Alcance del trabajo', 'pt': 'Escopo do trabalho'},
    'Notes / Instructions': {'es': 'Notas / instrucciones', 'pt': 'Notas / instrucoes'},
    'Save Schedule Entry': {'es': 'Guardar entrada de agenda', 'pt': 'Salvar entrada de agenda'},
    'Upcoming Assigned Jobs': {'es': 'Proximos trabajos asignados', 'pt': 'Proximos servicos atribuidos'},
    'Assigned': {'es': 'Asignado', 'pt': 'Atribuido'},
    'No schedule entries yet.': {'es': 'Aun no hay entradas de agenda.', 'pt': 'Ainda nao ha entradas de agenda.'},
    'Add a job schedule on the left to start assigning workers.': {'es': 'Agrega un trabajo a la izquierda para empezar a asignar trabajadores.', 'pt': 'Adicione um servico a esquerda para comecar a atribuir trabalhadores.'},
    'Saved Schedule Entries': {'es': 'Entradas de agenda guardadas', 'pt': 'Entradas de agenda salvas'},
    'Job': {'es': 'Trabajo', 'pt': 'Servico'},
    'Scope': {'es': 'Alcance', 'pt': 'Escopo'},
    'Time': {'es': 'Hora', 'pt': 'Hora'},
    'Action': {'es': 'Accion', 'pt': 'Acao'},
    'Delete': {'es': 'Eliminar', 'pt': 'Excluir'},
    'No schedule entries saved yet.': {'es': 'Aun no hay entradas de agenda guardadas.', 'pt': 'Ainda nao ha entradas de agenda salvas.'},
    'Unassigned': {'es': 'Sin asignar', 'pt': 'Sem atribuicao'},
    'How This Premium Flow Works': {'es': 'Como funciona este flujo premium', 'pt': 'Como este fluxo premium funciona'},
    'Clients -> Estimates -> Invoices': {'es': 'Clientes -> Presupuestos -> Facturas', 'pt': 'Clientes -> Orcamentos -> Faturas'},
    'Save repeat clients here once so their information is ready for future work.': {
        'es': 'Guarda aqui a los clientes recurrentes una vez para que su informacion quede lista para futuros trabajos.',
        'pt': 'Salve aqui os clientes recorrentes uma vez para que as informacoes fiquem prontas para trabalhos futuros.',
    },
    'Create the estimate first when the scope or price still needs approval.': {
        'es': 'Crea primero el presupuesto cuando el alcance o el precio aun necesiten aprobacion.',
        'pt': 'Crie primeiro o orcamento quando o escopo ou o preco ainda precisarem de aprovacao.',
    },
    'Send or copy the hosted estimate link so the client can review it online.': {
        'es': 'Envia o copia el link del presupuesto para que el cliente lo revise en linea.',
        'pt': 'Envie ou copie o link do orcamento para que o cliente o revise online.',
    },
    'Convert approved work into the final invoice when you are ready to collect payment.': {
        'es': 'Convierte el trabajo aprobado en la factura final cuando estes listo para cobrar.',
        'pt': 'Converta o trabalho aprovado na fatura final quando estiver pronto para cobrar.',
    },
    'Saved Client List': {'es': 'Lista de clientes guardados', 'pt': 'Lista de clientes salvos'},
    'Premium-only customer records for return business and faster quoting': {
        'es': 'Registros premium de clientes para trabajo recurrente y presupuestos mas rapidos',
        'pt': 'Registros premium de clientes para trabalho recorrente e orcamentos mais rapidos',
    },
    'Actions': {'es': 'Acciones', 'pt': 'Acoes'},
    'No email saved yet': {'es': 'Aun no hay correo guardado', 'pt': 'Ainda nao ha e-mail salvo'},
    'Edit': {'es': 'Editar', 'pt': 'Editar'},
    'Save Changes': {'es': 'Guardar cambios', 'pt': 'Salvar alteracoes'},
    'Archive': {'es': 'Archivar', 'pt': 'Arquivar'},
    'No saved clients yet. Add recurring customers here so estimates and invoices can reuse their details.': {
        'es': 'Aun no hay clientes guardados. Agrega aqui a los clientes recurrentes para reutilizar sus datos en presupuestos y facturas.',
        'pt': 'Ainda nao ha clientes salvos. Adicione aqui os clientes recorrentes para reutilizar os dados em orcamentos e faturas.',
    },
    'Sales Activity Snapshot': {'es': 'Resumen de actividad comercial', 'pt': 'Resumo da atividade comercial'},
    'Recent estimate and invoice relationships tied to your clients': {
        'es': 'Relaciones recientes de presupuestos y facturas vinculadas a tus clientes',
        'pt': 'Relacoes recentes de orcamentos e faturas ligadas aos seus clientes',
    },
    'Last Estimate': {'es': 'Ultimo presupuesto', 'pt': 'Ultimo orcamento'},
    'Last Invoice': {'es': 'Ultima factura', 'pt': 'Ultima fatura'},
    'Open Balance': {'es': 'Saldo abierto', 'pt': 'Saldo em aberto'},
    'No estimate or invoice activity yet.': {'es': 'Aun no hay actividad de presupuestos ni facturas.', 'pt': 'Ainda nao ha atividade de orcamentos nem faturas.'},
    'Hosted link and approval workflow': {'es': 'Link hospedado y flujo de aprobacion', 'pt': 'Link hospedado e fluxo de aprovacao'},
    'Hosted billing links and collection status': {'es': 'Links de cobro hospedados y estado de coleccion', 'pt': 'Links de cobranca hospedados e status de recebimento'},
    'Open Link': {'es': 'Abrir link', 'pt': 'Abrir link'},
    'Copy Link': {'es': 'Copiar link', 'pt': 'Copiar link'},
    'No estimates yet.': {'es': 'Aun no hay presupuestos.', 'pt': 'Ainda nao ha orcamentos.'},
    'No customer invoices yet.': {'es': 'Aun no hay facturas de clientes.', 'pt': 'Ainda nao ha faturas de clientes.'},
    'Archived Clients': {'es': 'Clientes archivados', 'pt': 'Clientes arquivados'},
    'Restore': {'es': 'Restaurar', 'pt': 'Restaurar'},
    'Copied': {'es': 'Copiado', 'pt': 'Copiado'},
    'Invoices & Income': {'es': 'Facturas e ingresos', 'pt': 'Faturas e receitas'},
    'Move from estimate to invoice in one premium sales workflow, then keep internal income records and mileage organized below.': {
        'es': 'Pasa del presupuesto a la factura en un solo flujo premium y mantiene abajo los ingresos internos y el kilometraje organizados.',
        'pt': 'Passe do orcamento para a fatura em um unico fluxo premium e mantenha abaixo as receitas internas e a quilometragem organizadas.',
    },
    'Track bookkeeping income records and mileage in one place. Customer-facing estimates, invoicing, and saved client tools are available on Premium.': {
        'es': 'Controla en un solo lugar los ingresos contables y el kilometraje. Los presupuestos, facturas y clientes guardados para clientes estan disponibles en Premium.',
        'pt': 'Acompanhe em um so lugar os registros contabeis de receita e a quilometragem. Orcamentos, faturamento e clientes salvos para atendimento ao cliente estao disponiveis no Premium.',
    },
    'Print This Page': {'es': 'Imprimir esta pagina', 'pt': 'Imprimir esta pagina'},
    'Estimate first, invoice second': {'es': 'Primero presupuesto, luego factura', 'pt': 'Primeiro orcamento, depois fatura'},
    'Hosted customer invoices': {'es': 'Facturas hospedadas para clientes', 'pt': 'Faturas hospedadas para clientes'},
    'Pay-online links supported': {'es': 'Links de pago online compatibles', 'pt': 'Links de pagamento online suportados'},
    'Automatic overdue reminders': {'es': 'Recordatorios automaticos por atraso', 'pt': 'Lembretes automaticos de atraso'},
    'Internal income records': {'es': 'Registros internos de ingresos', 'pt': 'Registros internos de receita'},
    'Mileage attachments': {'es': 'Adjuntos de kilometraje', 'pt': 'Anexos de quilometragem'},
    'Tax-ready bookkeeping': {'es': 'Contabilidad lista para impuestos', 'pt': 'Contabilidade pronta para impostos'},
    'Premium sales tools available': {'es': 'Herramientas premium de ventas disponibles', 'pt': 'Ferramentas premium de vendas disponiveis'},
    'Internal income records preserved': {'es': 'Registros internos preservados', 'pt': 'Registros internos preservados'},
    'overdue invoice reminder(s) were just sent automatically because this invoice center was opened.': {
        'es': 'recordatorio(s) de factura vencida se enviaron automaticamente al abrir este centro de facturas.',
        'pt': 'lembrete(s) de fatura vencida foram enviados automaticamente ao abrir esta central de faturas.',
    },
    'Use customer invoices for what clients receive. Keep internal income records below for tax-ready revenue tracking when you need bookkeeping-only entries.': {
        'es': 'Usa las facturas de clientes para lo que ellos reciben. Deja abajo los registros internos para el control contable cuando necesites movimientos solo de contabilidad.',
        'pt': 'Use faturas de clientes para o que eles recebem. Mantenha abaixo os registros internos para controle contabil quando precisar de lancamentos apenas de contabilidade.',
    },
    'This tier keeps bookkeeping income records available. Upgrade to Premium when you want saved clients, hosted estimates, customer invoices, and reminder automation.': {
        'es': 'Este plan mantiene disponibles los registros contables. Sube a Premium cuando quieras clientes guardados, presupuestos hospedados, facturas de clientes y recordatorios automaticos.',
        'pt': 'Este plano mantem disponiveis os registros contabeis. Faca upgrade para Premium quando quiser clientes salvos, orcamentos hospedados, faturas de clientes e lembretes automaticos.',
    },
    'Estimate Workflow': {'es': 'Flujo de presupuestos', 'pt': 'Fluxo de orcamentos'},
    'Wave-style flow': {'es': 'Flujo estilo Wave', 'pt': 'Fluxo estilo Wave'},
    'Create the quote first, send the hosted link, track whether the customer opened it, then convert approved work into the final invoice when you are ready to bill.': {
        'es': 'Crea primero el presupuesto, envia el link hospedado, confirma si el cliente lo abrio y luego convierte el trabajo aprobado en la factura final.',
        'pt': 'Crie primeiro o orcamento, envie o link hospedado, acompanhe se o cliente abriu e depois converta o trabalho aprovado na fatura final.',
    },
    'Draft': {'es': 'Borrador', 'pt': 'Rascunho'},
    'Sent / Viewed': {'es': 'Enviado / Visto', 'pt': 'Enviado / Visto'},
    'Converted': {'es': 'Convertido', 'pt': 'Convertido'},
    'Hosted links and send actions surfaced right here': {'es': 'Links hospedados y acciones de envio visibles aqui mismo', 'pt': 'Links hospedados e acoes de envio visiveis aqui mesmo'},
    'No estimates yet. Start with an estimate when you want the customer to review the scope before invoicing.': {
        'es': 'Aun no hay presupuestos. Empieza con un presupuesto cuando quieras que el cliente revise el alcance antes de facturar.',
        'pt': 'Ainda nao ha orcamentos. Comece com um orcamento quando quiser que o cliente revise o escopo antes de faturar.',
    },
    'Create Customer Invoice': {'es': 'Crear factura de cliente', 'pt': 'Criar fatura de cliente'},
    'Build a real customer invoice with line items, optional pay-online link, and a hosted invoice page that can be emailed right away. If the customer still needs approval first, use the estimate workflow above.': {
        'es': 'Crea una factura real con partidas, link opcional de pago online y pagina hospedada para enviarla enseguida. Si el cliente aun necesita aprobar primero, usa el flujo de presupuestos.',
        'pt': 'Monte uma fatura real com itens, link opcional de pagamento online e pagina hospedada para enviar na hora. Se o cliente ainda precisar aprovar antes, use o fluxo de orcamentos acima.',
    },
    'Saved Client': {'es': 'Cliente guardado', 'pt': 'Cliente salvo'},
    'Choose saved client (optional)': {'es': 'Elegir cliente guardado (opcional)', 'pt': 'Escolher cliente salvo (opcional)'},
    'Invoice Title': {'es': 'Titulo de la factura', 'pt': 'Titulo da fatura'},
    'Service Invoice': {'es': 'Factura de servicio', 'pt': 'Fatura de servico'},
    'Recipient Email': {'es': 'Correo del destinatario', 'pt': 'E-mail do destinatario'},
    'Customer Phone': {'es': 'Telefono del cliente', 'pt': 'Telefone do cliente'},
    'Customer Address': {'es': 'Direccion del cliente', 'pt': 'Endereco do cliente'},
    'Issue Date': {'es': 'Fecha de emision', 'pt': 'Data de emissao'},
    'Due Date': {'es': 'Fecha de vencimiento', 'pt': 'Data de vencimento'},
    'Online Payment Link': {'es': 'Link de pago online', 'pt': 'Link de pagamento online'},
    'https://stripe.com/... or hosted payment page': {'es': 'https://stripe.com/... o pagina de pago hospedada', 'pt': 'https://stripe.com/... ou pagina de pagamento hospedada'},
    'Sales Tax': {'es': 'Impuesto de ventas', 'pt': 'Imposto sobre vendas'},
    'Line Items': {'es': 'Partidas', 'pt': 'Itens'},
    'Qty': {'es': 'Cant.', 'pt': 'Qtd.'},
    'Unit Price': {'es': 'Precio unitario', 'pt': 'Preco unitario'},
    'Line Total': {'es': 'Total de linea', 'pt': 'Total da linha'},
    'Service, visit, project phase, or item': {'es': 'Servicio, visita, fase del proyecto o partida', 'pt': 'Servico, visita, fase do projeto ou item'},
    'Subtotal': {'es': 'Subtotal', 'pt': 'Subtotal'},
    'Total Invoice': {'es': 'Total de la factura', 'pt': 'Total da fatura'},
    'Optional invoice message, scope summary, or payment note': {
        'es': 'Mensaje opcional de la factura, resumen del alcance o nota de pago',
        'pt': 'Mensagem opcional da fatura, resumo do escopo ou nota de pagamento',
    },
    'Send invoice email immediately after saving': {'es': 'Enviar la factura por correo inmediatamente despues de guardar', 'pt': 'Enviar a fatura por e-mail logo apos salvar'},
    'Save Customer Invoice': {'es': 'Guardar factura del cliente', 'pt': 'Salvar fatura do cliente'},
    'Premium Invoice Tools': {'es': 'Herramientas premium de facturas', 'pt': 'Ferramentas premium de faturas'},
    'Saved Clients + Reminders': {'es': 'Clientes guardados + recordatorios', 'pt': 'Clientes salvos + lembretes'},
    'Choose a saved client to reuse email and address details instantly.': {
        'es': 'Elige un cliente guardado para reutilizar al instante el correo y la direccion.',
        'pt': 'Escolha um cliente salvo para reutilizar imediatamente o e-mail e o endereco.',
    },
    'Add a pay-online link when you want the invoice page to include a payment button.': {
        'es': 'Agrega un link de pago online cuando quieras que la factura incluya un boton de pago.',
        'pt': 'Adicione um link de pagamento online quando quiser que a fatura inclua um botao de pagamento.',
    },
    'Use reminders only for open balances so repeat follow-up stays organized.': {
        'es': 'Usa recordatorios solo para saldos abiertos y manten organizado el seguimiento.',
        'pt': 'Use lembretes apenas para saldos em aberto e mantenha o acompanhamento organizado.',
    },
    'Keep bookkeeping-only income below when money is received outside the hosted invoice flow.': {
        'es': 'Mantiene abajo los ingresos solo contables cuando el dinero llega fuera del flujo hospedado de facturas.',
        'pt': 'Mantenha abaixo as receitas apenas contabeis quando o dinheiro entrar fora do fluxo hospedado de faturas.',
    },
    'Saved Customer Invoices': {'es': 'Facturas guardadas de clientes', 'pt': 'Faturas salvas de clientes'},
    'Hosted invoice pages, reminders, and pay-online links': {'es': 'Paginas hospedadas, recordatorios y links de pago online', 'pt': 'Paginas hospedadas, lembretes e links de pagamento online'},
    'Invoice #': {'es': 'Factura #', 'pt': 'Fatura #'},
    'Paid': {'es': 'Pagado', 'pt': 'Pago'},
    'Balance': {'es': 'Saldo', 'pt': 'Saldo'},
    'Due': {'es': 'Vence', 'pt': 'Vence'},
    'Open Hosted': {'es': 'Abrir hospedado', 'pt': 'Abrir hospedado'},
    'Send': {'es': 'Enviar', 'pt': 'Enviar'},
    'Reminder': {'es': 'Recordatorio', 'pt': 'Lembrete'},
    'Mark Paid': {'es': 'Marcar pagado', 'pt': 'Marcar como pago'},
    'Closed': {'es': 'Cerrado', 'pt': 'Fechado'},
    'No customer invoices saved yet.': {'es': 'Aun no hay facturas de clientes guardadas.', 'pt': 'Ainda nao ha faturas de clientes salvas.'},
    'Premium Sales Tools': {'es': 'Herramientas premium de ventas', 'pt': 'Ferramentas premium de vendas'},
    'Upgrade Required': {'es': 'Upgrade requerido', 'pt': 'Upgrade necessario'},
    'Saved clients, estimates, customer invoices, pay-online links, and reminder automation are locked to the Premium subscription.': {
        'es': 'Los clientes guardados, presupuestos, facturas de clientes, links de pago online y automatizacion de recordatorios estan bloqueados para la suscripcion Premium.',
        'pt': 'Clientes salvos, orcamentos, faturas de clientes, links de pagamento online e automacao de lembretes ficam bloqueados na assinatura Premium.',
    },
    'Saved client list': {'es': 'Lista de clientes guardados', 'pt': 'Lista de clientes salvos'},
    'Hosted estimates': {'es': 'Presupuestos hospedados', 'pt': 'Orcamentos hospedados'},
    'Customer invoices': {'es': 'Facturas de clientes', 'pt': 'Faturas de clientes'},
    'Automatic reminders': {'es': 'Recordatorios automaticos', 'pt': 'Lembretes automaticos'},
    'Upgrade to Premium': {'es': 'Subir a Premium', 'pt': 'Fazer upgrade para Premium'},
    'Create Internal Income Record': {'es': 'Crear registro interno de ingreso', 'pt': 'Criar registro interno de receita'},
    'Use this when you need a bookkeeping-only revenue entry that is not being sent to a customer as an invoice.': {
        'es': 'Usa esto cuando necesites un ingreso solo contable que no sera enviado al cliente como factura.',
        'pt': 'Use isto quando precisar de um lancamento de receita apenas contabil que nao sera enviado ao cliente como fatura.',
    },
    'Income Type': {'es': 'Tipo de ingreso', 'pt': 'Tipo de receita'},
    'Gross Income Received': {'es': 'Ingreso bruto recibido', 'pt': 'Receita bruta recebida'},
    'Income Source / Customer': {'es': 'Origen del ingreso / Cliente', 'pt': 'Origem da receita / Cliente'},
    'Service Address / Sale Location': {'es': 'Direccion del servicio / lugar de la venta', 'pt': 'Endereco do servico / local da venda'},
    'Date Received': {'es': 'Fecha de recepcion', 'pt': 'Data de recebimento'},
    'Sales Tax Portion': {'es': 'Parte del impuesto de ventas', 'pt': 'Parcela do imposto sobre vendas'},
    'Sales tax on this record has already been paid / remitted': {'es': 'El impuesto de ventas de este registro ya fue pagado / remitido', 'pt': 'O imposto sobre vendas deste registro ja foi pago / recolhido'},
    'Service performed, payment source, tax note, or internal documentation': {
        'es': 'Servicio realizado, origen del pago, nota fiscal o documentacion interna',
        'pt': 'Servico realizado, origem do pagamento, nota fiscal ou documentacao interna',
    },
    'Save Income Record': {'es': 'Guardar registro de ingreso', 'pt': 'Salvar registro de receita'},
    'Income Mileage Attachment': {'es': 'Adjunto de kilometraje del ingreso', 'pt': 'Anexo de quilometragem da receita'},
    'Attach deductible travel only when you need to tie mileage to a saved internal income record.': {
        'es': 'Adjunta solo viajes deducibles cuando necesites vincular kilometraje a un registro interno guardado.',
        'pt': 'Anexe apenas viagens dedutiveis quando precisar vincular a quilometragem a um registro interno salvo.',
    },
    'Income Record': {'es': 'Registro de ingreso', 'pt': 'Registro de receita'},
    'Select saved record': {'es': 'Selecciona un registro guardado', 'pt': 'Selecione um registro salvo'},
    'Trip Date': {'es': 'Fecha del trayecto', 'pt': 'Data do trajeto'},
    'Starting Point': {'es': 'Punto de inicio', 'pt': 'Ponto de partida'},
    'Destination': {'es': 'Destino', 'pt': 'Destino'},
    'Customer or job address': {'es': 'Direccion del cliente o del trabajo', 'pt': 'Endereco do cliente ou do servico'},
    'Trip Type': {'es': 'Tipo de trayecto', 'pt': 'Tipo de trajeto'},
    'Two-way': {'es': 'Ida y vuelta', 'pt': 'Ida e volta'},
    'One-way': {'es': 'Solo ida', 'pt': 'Somente ida'},
    'Number of Round Trips': {'es': 'Numero de viajes completos', 'pt': 'Numero de viagens completas'},
    'One-Way Miles': {'es': 'Millas de ida', 'pt': 'Milhas de ida'},
    'Leave blank to auto-estimate': {'es': 'Dejar en blanco para estimar automaticamente', 'pt': 'Deixe em branco para estimar automaticamente'},
    'Rate / Cost': {'es': 'Tarifa / costo', 'pt': 'Taxa / custo'},
    'Total Miles': {'es': 'Millas totales', 'pt': 'Milhas totais'},
    'Total Mileage Amount': {'es': 'Valor total del kilometraje', 'pt': 'Valor total da quilometragem'},
    'Optional job or trip note': {'es': 'Nota opcional del trabajo o trayecto', 'pt': 'Nota opcional do servico ou trajeto'},
    'Save Mileage Attachment': {'es': 'Guardar adjunto de kilometraje', 'pt': 'Salvar anexo de quilometragem'},
    'Saved Income Records': {'es': 'Registros internos guardados', 'pt': 'Registros internos salvos'},
    'Bookkeeping-only received income entries': {'es': 'Entradas de ingreso recibidas solo para contabilidad', 'pt': 'Lancamentos de receita recebida apenas para contabilidade'},
    'Record #': {'es': 'Registro #', 'pt': 'Registro #'},
    'Source': {'es': 'Origen', 'pt': 'Origem'},
    'Gross': {'es': 'Bruto', 'pt': 'Bruto'},
    'Tax Status': {'es': 'Estado fiscal', 'pt': 'Status fiscal'},
    'Service Income': {'es': 'Ingreso por servicio', 'pt': 'Receita de servico'},
    'Paid / Remitted': {'es': 'Pagado / remitido', 'pt': 'Pago / recolhido'},
    'Not marked paid': {'es': 'No marcado como pagado', 'pt': 'Nao marcado como pago'},
    'Print Record': {'es': 'Imprimir registro', 'pt': 'Imprimir registro'},
    'No internal income records saved yet.': {'es': 'Aun no hay registros internos guardados.', 'pt': 'Ainda nao ha registros internos salvos.'},
    'Saved Mileage Attachments': {'es': 'Adjuntos de kilometraje guardados', 'pt': 'Anexos de quilometragem salvos'},
    'Mileage entries tied to internal income records': {'es': 'Entradas de kilometraje vinculadas a registros internos', 'pt': 'Lancamentos de quilometragem vinculados a registros internos'},
    'Route': {'es': 'Ruta', 'pt': 'Rota'},
    'No mileage attachments saved yet.': {'es': 'Aun no hay adjuntos de kilometraje guardados.', 'pt': 'Ainda nao ha anexos de quilometragem salvos.'},
    'sent': {'es': 'enviado', 'pt': 'enviado'},
    'viewed': {'es': 'visto', 'pt': 'visto'},
    'reminder': {'es': 'recordatorio', 'pt': 'lembrete'},
    'items': {'es': 'items', 'pt': 'itens'},
    'Create polished project estimates, send the hosted estimate link, track customer response, and convert approved work into a real customer invoice without rebuilding line items.': {
        'es': 'Crea presupuestos pulidos, envia el link hospedado, sigue la respuesta del cliente y convierte el trabajo aprobado en una factura real sin rehacer las partidas.',
        'pt': 'Crie orcamentos refinados, envie o link hospedado, acompanhe a resposta do cliente e converta o trabalho aprovado em uma fatura real sem refazer os itens.',
    },
    'Hosted estimate page': {'es': 'Pagina hospedada del presupuesto', 'pt': 'Pagina hospedada do orcamento'},
    'Customer approve / decline': {'es': 'Cliente aprueba / rechaza', 'pt': 'Cliente aprova / recusa'},
    'Convert to invoice': {'es': 'Convertir en factura', 'pt': 'Converter em fatura'},
    'Saved clients supported': {'es': 'Compatible con clientes guardados', 'pt': 'Compativel com clientes salvos'},
    'Use estimates before billing starts. Once the customer approves, convert the estimate into a customer invoice without rebuilding the line items.': {
        'es': 'Usa presupuestos antes de empezar a cobrar. Una vez aprobado por el cliente, conviertelo en factura sin rehacer las partidas.',
        'pt': 'Use orcamentos antes de iniciar a cobranca. Depois que o cliente aprovar, converta em fatura sem refazer os itens.',
    },
    'Estimate Pipeline': {'es': 'Pipeline de presupuestos', 'pt': 'Pipeline de orcamentos'},
    'Hosted Sales Flow': {'es': 'Flujo de ventas hospedado', 'pt': 'Fluxo de vendas hospedado'},
    'Total': {'es': 'Total', 'pt': 'Total'},
    'The stronger sales pattern is simple: create estimate, send hosted link, wait for approval, then convert to invoice when the work is ready to bill.': {
        'es': 'El mejor patron de ventas es simple: crea el presupuesto, envia el link hospedado, espera la aprobacion y luego convierte a factura cuando el trabajo este listo para cobrar.',
        'pt': 'O padrao de vendas mais forte e simples: crie o orcamento, envie o link hospedado, espere a aprovacao e depois converta em fatura quando o trabalho estiver pronto para cobrar.',
    },
    'Best Use': {'es': 'Mejor uso', 'pt': 'Melhor uso'},
    'Premium Workflow': {'es': 'Flujo premium', 'pt': 'Fluxo premium'},
    'Choose a saved client first when this is repeat business.': {
        'es': 'Elige primero un cliente guardado cuando sea un trabajo recurrente.',
        'pt': 'Escolha primeiro um cliente salvo quando for um trabalho recorrente.',
    },
    'Create the estimate with the real scope, pricing, and valid-until date.': {
        'es': 'Crea el presupuesto con el alcance real, el precio y la fecha de validez.',
        'pt': 'Crie o orcamento com o escopo real, o preco e a data de validade.',
    },
    'Send the hosted estimate link so the customer can review it cleanly online.': {
        'es': 'Envia el link del presupuesto para que el cliente lo revise claramente en linea.',
        'pt': 'Envie o link do orcamento para que o cliente o revise online com clareza.',
    },
    'Convert the approved estimate into an invoice when you are ready to collect payment.': {
        'es': 'Convierte el presupuesto aprobado en factura cuando estes listo para cobrar.',
        'pt': 'Converta o orcamento aprovado em fatura quando estiver pronto para cobrar.',
    },
    'Build the scope, email the hosted estimate link right away, and let the customer approve or decline it from a clean page.': {
        'es': 'Define el alcance, envia de inmediato el link del presupuesto y deja que el cliente apruebe o rechace desde una pagina limpia.',
        'pt': 'Monte o escopo, envie imediatamente o link do orcamento e deixe o cliente aprovar ou recusar em uma pagina limpa.',
    },
    'Estimate Title': {'es': 'Titulo del presupuesto', 'pt': 'Titulo do orcamento'},
    'Project Estimate': {'es': 'Presupuesto del proyecto', 'pt': 'Orcamento do projeto'},
    'Estimate Date': {'es': 'Fecha del presupuesto', 'pt': 'Data do orcamento'},
    'Valid Until': {'es': 'Valido hasta', 'pt': 'Valido ate'},
    'Service, visit, scope item, or phase': {'es': 'Servicio, visita, partida del alcance o fase', 'pt': 'Servico, visita, item do escopo ou fase'},
    'Total Estimate': {'es': 'Total del presupuesto', 'pt': 'Total do orcamento'},
    'Scope note, exclusions, or customer-facing context': {
        'es': 'Nota de alcance, exclusiones o contexto visible para el cliente',
        'pt': 'Nota de escopo, exclusoes ou contexto visivel para o cliente',
    },
    'Send hosted estimate link immediately after saving': {'es': 'Enviar el link del presupuesto inmediatamente despues de guardar', 'pt': 'Enviar o link do orcamento logo apos salvar'},
    'Save Estimate': {'es': 'Guardar presupuesto', 'pt': 'Salvar orcamento'},
    'Hosted Link Actions': {'es': 'Acciones del link hospedado', 'pt': 'Acoes do link hospedado'},
    'Send · Copy · Convert': {'es': 'Enviar · Copiar · Convertir', 'pt': 'Enviar · Copiar · Converter'},
    'Every saved estimate keeps a hosted customer page. Use the quick actions below to open it, copy the link, resend it, or convert approved work into an invoice.': {
        'es': 'Cada presupuesto guardado mantiene una pagina hospedada. Usa las acciones rapidas para abrirlo, copiar el link, reenviarlo o convertir el trabajo aprobado en factura.',
        'pt': 'Cada orcamento salvo mantem uma pagina hospedada. Use as acoes rapidas para abrir, copiar o link, reenviar ou converter o trabalho aprovado em fatura.',
    },
    'Open Invoice Center': {'es': 'Abrir central de facturas', 'pt': 'Abrir central de faturas'},
    'Create New Estimate': {'es': 'Crear nuevo presupuesto', 'pt': 'Criar novo orcamento'},
    'Saved Estimates': {'es': 'Presupuestos guardados', 'pt': 'Orcamentos salvos'},
    'Hosted estimates waiting for customer response or ready for invoice conversion': {
        'es': 'Presupuestos hospedados esperando respuesta del cliente o listos para convertirse en factura',
        'pt': 'Orcamentos hospedados aguardando resposta do cliente ou prontos para conversao em fatura',
    },
    'Estimate #': {'es': 'Presupuesto #', 'pt': 'Orcamento #'},
    'Hosted Link': {'es': 'Link hospedado', 'pt': 'Link hospedado'},
    'Send Estimate': {'es': 'Enviar presupuesto', 'pt': 'Enviar orcamento'},
    'Convert to Invoice': {'es': 'Convertir en factura', 'pt': 'Converter em fatura'},
    'Open Invoice': {'es': 'Abrir factura', 'pt': 'Abrir fatura'},
    'No estimates saved yet.': {'es': 'Aun no hay presupuestos guardados.', 'pt': 'Ainda nao ha orcamentos salvos.'},
})

TRANSLATIONS.update({
    'English': {'es': 'Ingles', 'pt': 'Ingles'},
    'Español': {'es': 'Español', 'pt': 'Espanhol'},
    'Português': {'es': 'Portugués', 'pt': 'Português'},
    'Show': {'es': 'Mostrar', 'pt': 'Mostrar'},
    'Hide': {'es': 'Ocultar', 'pt': 'Ocultar'},
    'Show password': {'es': 'Mostrar contraseña', 'pt': 'Mostrar senha'},
    'Hide password': {'es': 'Ocultar contraseña', 'pt': 'Ocultar senha'},
    'Jobs': {'es': 'Trabajos', 'pt': 'Servicos'},
    'Dispatch': {'es': 'Despacho', 'pt': 'Despacho'},
    'Schedule': {'es': 'Calendario', 'pt': 'Agenda'},
    'Team': {'es': 'Equipo', 'pt': 'Equipe'},
    'Availability': {'es': 'Disponibilidad', 'pt': 'Disponibilidade'},
    'Activity': {'es': 'Actividad', 'pt': 'Atividade'},
    'Invite Access': {'es': 'Acceso por invitacion', 'pt': 'Acesso por convite'},
    'Secure Setup': {'es': 'Configuracion segura', 'pt': 'Configuracao segura'},
    'Business Login': {'es': 'Acceso del negocio', 'pt': 'Login da empresa'},
    'Guided Access': {'es': 'Acceso guiado', 'pt': 'Acesso guiado'},
    'Account Setup': {'es': 'Configuracion de cuenta', 'pt': 'Configuracao de conta'},
    'Create your business login': {'es': 'Crea tu acceso empresarial', 'pt': 'Crie o login da sua empresa'},
    'Business accounts are created with an invite link sent by your administrator. This keeps access restricted to approved businesses only.': {
        'es': 'Las cuentas empresariales se crean con un link de invitacion enviado por tu administrador. Esto mantiene el acceso restringido solo a negocios aprobados.',
        'pt': 'As contas empresariais sao criadas com um link de convite enviado pelo seu administrador. Isso mantem o acesso restrito apenas a empresas aprovadas.',
    },
    'How to create your account': {'es': 'Como crear tu cuenta', 'pt': 'Como criar sua conta'},
    'Ask your administrator to send your invite email.': {'es': 'Pide a tu administrador que envie tu correo de invitacion.', 'pt': 'Peca ao seu administrador para enviar o email de convite.'},
    'Open the invite link from that email.': {'es': 'Abre el link de invitacion de ese correo.', 'pt': 'Abra o link de convite desse email.'},
    'Enter your name, email, and password.': {'es': 'Ingresa tu nombre, correo y contraseña.', 'pt': 'Digite seu nome, email e senha.'},
    'Return to the login page and sign in.': {'es': 'Vuelve a la pagina de acceso e inicia sesion.', 'pt': 'Volte para a pagina de login e entre.'},
    'Back to Login': {'es': 'Volver al login', 'pt': 'Voltar ao login'},
    'Forgot Password': {'es': 'Olvide mi contraseña', 'pt': 'Esqueci minha senha'},
    'Password Reset': {'es': 'Restablecer contraseña', 'pt': 'Redefinir senha'},
    'Submit Reset Request': {'es': 'Enviar solicitud de restablecimiento', 'pt': 'Enviar solicitacao de redefinicao'},
    'Back to Main Login': {'es': 'Volver al login principal', 'pt': 'Voltar ao login principal'},
    'Reset Password': {'es': 'Restablecer contraseña', 'pt': 'Redefinir senha'},
    'Set New Password': {'es': 'Definir nueva contraseña', 'pt': 'Definir nova senha'},
    'Choose a new password for your LedgerFlow account.': {'es': 'Elige una nueva contraseña para tu cuenta de LedgerFlow.', 'pt': 'Escolha uma nova senha para sua conta LedgerFlow.'},
    'New Password': {'es': 'Nueva contraseña', 'pt': 'Nova senha'},
    'Confirm New Password': {'es': 'Confirmar nueva contraseña', 'pt': 'Confirmar nova senha'},
    'Save New Password': {'es': 'Guardar nueva contraseña', 'pt': 'Salvar nova senha'},
    'Restore Workspace Access': {'es': 'Restaurar acceso al espacio de trabajo', 'pt': 'Restaurar acesso ao espaco de trabalho'},
    'Rejoin': {'es': 'Regresar', 'pt': 'Retornar'},
    'Workspace': {'es': 'Espacio de trabajo', 'pt': 'Workspace'},
    'Return': {'es': 'Volver', 'pt': 'Retornar'},
    'Return to LedgerFlow': {'es': 'Volver a LedgerFlow', 'pt': 'Voltar para LedgerFlow'},
    'Restore your business workspace access': {'es': 'Restaura el acceso al espacio de trabajo de tu negocio', 'pt': 'Restaure o acesso ao workspace da sua empresa'},
    'LedgerFlow can bring {business_name} back online without rebuilding your records. Use this step to restore access safely and continue with your normal workspace.': {
        'es': 'LedgerFlow puede volver a poner {business_name} en linea sin reconstruir tus registros. Usa este paso para restaurar el acceso de forma segura y continuar con tu workspace normal.',
        'pt': 'O LedgerFlow pode colocar {business_name} de volta online sem reconstruir seus registros. Use esta etapa para restaurar o acesso com seguranca e continuar com seu workspace normal.',
    },
    'Restore access': {'es': 'Restaurar acceso', 'pt': 'Restaurar acesso'},
    'Reactivate the archived workspace record.': {'es': 'Reactiva el registro archivado del espacio de trabajo.', 'pt': 'Reative o registro arquivado do workspace.'},
    'Continue securely': {'es': 'Continuar con seguridad', 'pt': 'Continuar com seguranca'},
    'Sign back in with your existing business login.': {'es': 'Vuelve a entrar con tu acceso empresarial existente.', 'pt': 'Entre novamente com o login empresarial ja existente.'},
    'Create your business login if one has not been created yet.': {'es': 'Crea tu acceso empresarial si aun no existe.', 'pt': 'Crie o login da empresa se ele ainda nao existir.'},
    'Resume operations': {'es': 'Retomar operaciones', 'pt': 'Retomar operacoes'},
    'Return to billing, income records, payroll tools, and the business calendar.': {'es': 'Vuelve a facturacion, registros de ingresos, herramientas de nomina y calendario del negocio.', 'pt': 'Volte para cobranca, registros de renda, ferramentas de folha e calendario da empresa.'},
    'Workspace Rejoin': {'es': 'Reingreso al workspace', 'pt': 'Retorno ao workspace'},
    'Restore access for {business_name}': {'es': 'Restaurar acceso para {business_name}', 'pt': 'Restaurar acesso para {business_name}'},
    'This rejoin link has expired. Ask your administrator to send a new one.': {'es': 'Este link de reingreso ha expirado. Pide a tu administrador que envie uno nuevo.', 'pt': 'Este link de retorno expirou. Peca ao seu administrador para enviar um novo.'},
    'This workspace has already been restored. Sign in below to continue.': {'es': 'Este espacio de trabajo ya fue restaurado. Inicia sesion abajo para continuar.', 'pt': 'Este workspace ja foi restaurado. Entre abaixo para continuar.'},
    'We found an existing business login for this workspace. Restore access, then sign in with your current email.': {'es': 'Encontramos un acceso empresarial existente para este espacio de trabajo. Restaura el acceso y luego entra con tu correo actual.', 'pt': 'Encontramos um login empresarial existente para este workspace. Restaure o acesso e depois entre com seu email atual.'},
    'Restore the workspace first, then continue into secure business login creation.': {'es': 'Restaura primero el espacio de trabajo y luego continua con la creacion segura del acceso empresarial.', 'pt': 'Restaure primeiro o workspace e depois continue para a criacao segura do login empresarial.'},
    'Status': {'es': 'Estado', 'pt': 'Status'},
    'Existing Login': {'es': 'Acceso existente', 'pt': 'Login existente'},
    'Restore and Sign In': {'es': 'Restaurar e iniciar sesion', 'pt': 'Restaurar e entrar'},
    'Restore and Continue': {'es': 'Restaurar y continuar', 'pt': 'Restaurar e continuar'},
    'Open Login': {'es': 'Abrir login', 'pt': 'Abrir login'},
    'Workspace Status': {'es': 'Estado del workspace', 'pt': 'Status do workspace'},
    'We Missed You': {'es': 'Te echamos de menos', 'pt': 'Sentimos sua falta'},
    'Income Records': {'es': 'Registros de ingresos', 'pt': 'Registros de renda'},
    'Come Back': {'es': 'Volver', 'pt': 'Voltar'},
    'Welcome back, {full_name}': {'es': 'Bienvenido de nuevo, {full_name}', 'pt': 'Bem-vindo de volta, {full_name}'},
    'LedgerFlow Workspace': {'es': 'Workspace LedgerFlow', 'pt': 'Workspace LedgerFlow'},
    'Access is paused for now': {'es': 'El acceso esta pausado por ahora', 'pt': 'O acesso esta pausado por enquanto'},
    'What to do next': {'es': 'Que hacer ahora', 'pt': 'O que fazer agora'},
    'Contact your LedgerFlow administrator to restore access.': {'es': 'Contacta a tu administrador de LedgerFlow para restaurar el acceso.', 'pt': 'Entre em contato com o administrador do LedgerFlow para restaurar o acesso.'},
    'Once your workspace is reactivated, you can sign back in and continue where you left off.': {'es': 'Cuando tu workspace se reactive, podras volver a entrar y continuar donde lo dejaste.', 'pt': 'Quando seu workspace for reativado, voce podera entrar novamente e continuar de onde parou.'},
    'Sign Out': {'es': 'Cerrar sesion', 'pt': 'Sair'},
    'Language saved: {language_label}.': {'es': 'Idioma guardado: {language_label}.', 'pt': 'Idioma salvo: {language_label}.'},
    'Full name is required.': {'es': 'El nombre completo es obligatorio.', 'pt': 'O nome completo e obrigatorio.'},
    'Email is required.': {'es': 'El correo es obligatorio.', 'pt': 'O email e obrigatorio.'},
    'Password must be at least 8 characters.': {'es': 'La contraseña debe tener al menos 8 caracteres.', 'pt': 'A senha deve ter pelo menos 8 caracteres.'},
    'Passwords do not match.': {'es': 'Las contraseñas no coinciden.', 'pt': 'As senhas nao coincidem.'},
    'Email already exists.': {'es': 'Ese correo ya existe.', 'pt': 'Esse email ja existe.'},
    'Administrator account created. Sign in below.': {'es': 'Cuenta de administrador creada. Inicia sesion abajo.', 'pt': 'Conta de administrador criada. Entre abaixo.'},
    'Invalid email or password.': {'es': 'Correo o contraseña invalidos.', 'pt': 'Email ou senha invalidos.'},
    'Worker portal access is pending administrator approval.': {'es': 'El acceso al portal del trabajador esta pendiente de aprobacion del administrador.', 'pt': 'O acesso ao portal do trabalhador esta aguardando aprovacao do administrador.'},
    'Worker portal access needs correction from the business before you can sign in.': {'es': 'El acceso al portal del trabajador necesita correccion del negocio antes de iniciar sesion.', 'pt': 'O acesso ao portal do trabalhador precisa de correcao da empresa antes do login.'},
    'Team member portal access is no longer active.': {'es': 'El acceso del portal del miembro del equipo ya no esta activo.', 'pt': 'O acesso do portal do membro da equipe nao esta mais ativo.'},
    'Team member portal access is pending administrator approval.': {'es': 'El acceso del portal del miembro del equipo esta pendiente de aprobacion del administrador.', 'pt': 'O acesso do portal do membro da equipe esta aguardando aprovacao do administrador.'},
    'Team member portal access needs correction before you can sign in.': {'es': 'El acceso del portal del miembro del equipo necesita correccion antes de iniciar sesion.', 'pt': 'O acesso do portal do membro da equipe precisa de correcao antes do login.'},
    'Invalid team member email or password.': {'es': 'Correo o contraseña del miembro del equipo invalidos.', 'pt': 'Email ou senha do membro da equipe invalidos.'},
    'If the email exists in {app_name}, a password reset request has been submitted. Check your email if delivery is enabled, or contact your administrator.': {
        'es': 'Si el correo existe en {app_name}, se envio una solicitud para restablecer la contraseña. Revisa tu correo si la entrega esta habilitada o contacta a tu administrador.',
        'pt': 'Se o email existir no {app_name}, uma solicitacao de redefinicao de senha foi enviada. Verifique seu email se o envio estiver habilitado ou fale com seu administrador.',
    },
    'This reset link is invalid or has already been used.': {'es': 'Este link de restablecimiento es invalido o ya fue usado.', 'pt': 'Este link de redefinicao e invalido ou ja foi usado.'},
    'This reset link has expired. Submit a new reset request.': {'es': 'Este link de restablecimiento expirou. Envia una nueva solicitud.', 'pt': 'Este link de redefinicao expirou. Envie uma nova solicitacao.'},
    'Password reset complete. Sign in with your new password.': {'es': 'Restablecimiento completo. Inicia sesion con tu nueva contraseña.', 'pt': 'Redefinicao concluida. Entre com sua nova senha.'},
    'That email already has an account. Sign in instead, or use Forgot Password if needed.': {'es': 'Ese correo ya tiene una cuenta. Inicia sesion o usa Olvide mi contraseña si es necesario.', 'pt': 'Esse email ja tem uma conta. Entre normalmente ou use Esqueci minha senha se precisar.'},
    'Trial claimed. Start in the Welcome Center, review the guided overview, and finish the quick setup when you are ready.': {
        'es': 'Prueba activada. Empieza en el Centro de Bienvenida, revisa la guia y termina la configuracion rapida cuando estes listo.',
        'pt': 'Teste ativado. Comece no Centro de Boas-Vindas, revise a orientacao guiada e termine a configuracao rapida quando estiver pronto.',
    },
    'Business login created. Complete setup to unlock your full LedgerFlow workspace.': {
        'es': 'Acceso empresarial creado. Completa la configuracion para desbloquear todo tu workspace LedgerFlow.',
        'pt': 'Login empresarial criado. Complete a configuracao para liberar todo o seu workspace LedgerFlow.',
    },
    'Trial claimed. Your LedgerFlow workspace is ready to explore.': {'es': 'Prueba activada. Tu workspace de LedgerFlow esta listo para explorar.', 'pt': 'Teste ativado. Seu workspace LedgerFlow esta pronto para explorar.'},
    'Business login created. Welcome email sent. Sign in below.': {'es': 'Acceso empresarial creado. El email de bienvenida fue enviado. Inicia sesion abajo.', 'pt': 'Login empresarial criado. O email de boas-vindas foi enviado. Entre abaixo.'},
    'Business login created, but welcome email failed: {error_message}': {'es': 'El acceso empresarial fue creado, pero fallo el email de bienvenida: {error_message}', 'pt': 'O login empresarial foi criado, mas o email de boas-vindas falhou: {error_message}'},
    'Business login created. Sign in below.': {'es': 'Acceso empresarial creado. Inicia sesion abajo.', 'pt': 'Login empresarial criado. Entre abaixo.'},
    'Your LedgerFlow workspace has been restored. Sign in to continue.': {'es': 'Tu workspace de LedgerFlow fue restaurado. Inicia sesion para continuar.', 'pt': 'Seu workspace LedgerFlow foi restaurado. Entre para continuar.'},
    'Workspace restored. Create your business login to continue.': {'es': 'Workspace restaurado. Crea tu acceso empresarial para continuar.', 'pt': 'Workspace restaurado. Crie seu login empresarial para continuar.'},
    'Start Your Trial': {'es': 'Empieza tu prueba', 'pt': 'Comece seu teste'},
    'Create Business Login': {'es': 'Crear acceso empresarial', 'pt': 'Criar login empresarial'},
    'Secure Access': {'es': 'Acceso seguro', 'pt': 'Acesso seguro'},
    'Subscription': {'es': 'Suscripcion', 'pt': 'Assinatura'},
    'Upgrade Later': {'es': 'Mejorar despues', 'pt': 'Fazer upgrade depois'},
    'Billing Ready': {'es': 'Facturacion lista', 'pt': 'Cobranca pronta'},
    'Complimentary Trial': {'es': 'Prueba gratuita', 'pt': 'Teste gratuito'},
    '{trial_offer_days}-Day Trial': {'es': 'Prueba de {trial_offer_days} dias', 'pt': 'Teste de {trial_offer_days} dias'},
    'Start your {trial_offer_days}-day LedgerFlow trial': {'es': 'Empieza tu prueba de {trial_offer_days} dias de LedgerFlow', 'pt': 'Comece seu teste de {trial_offer_days} dias do LedgerFlow'},
    'A cleaner guided start for {business_name}: review the workspace experience, explore the subscription tiers, create secure access, and continue the trial now. Upgrade later when you are ready.': {
        'es': 'Un inicio guiado y mas limpio para {business_name}: revisa la experiencia del workspace, explora los niveles de suscripcion, crea acceso seguro y continua la prueba ahora. Mejora despues cuando estes listo.',
        'pt': 'Um inicio guiado e mais organizado para {business_name}: revise a experiencia do workspace, explore os niveis de assinatura, crie acesso seguro e continue o teste agora. Faca upgrade depois quando estiver pronto.',
    },
    '{trial_offer_days} Days': {'es': '{trial_offer_days} dias', 'pt': '{trial_offer_days} dias'},
    'No card required to begin': {'es': 'No se requiere tarjeta para empezar', 'pt': 'Nenhum cartao e necessario para comecar'},
    'Video tutorial ready': {'es': 'Tutorial en video listo', 'pt': 'Tutorial em video pronto'},
    'Choose subscription now': {'es': 'Elige la suscripcion ahora', 'pt': 'Escolha a assinatura agora'},
    'Upgrade later': {'es': 'Mejora despues', 'pt': 'Faca upgrade depois'},
    'Welcome Tutorial Preview': {'es': 'Vista previa del tutorial de bienvenida', 'pt': 'Previa do tutorial de boas-vindas'},
    'Drop your marketing or welcome video here later': {'es': 'Coloca aqui tu video de marketing o bienvenida mas tarde', 'pt': 'Coloque aqui seu video de marketing ou boas-vindas depois'},
    'This top section is reserved for the welcome/tutorial video that introduces the workspace, explains the 7-day complimentary period, and shows the first steps clearly.': {
        'es': 'Esta seccion superior esta reservada para el video de bienvenida/tutorial que presenta el workspace, explica el periodo de 7 dias y muestra claramente los primeros pasos.',
        'pt': 'Esta secao superior fica reservada para o video de boas-vindas/tutorial que apresenta o workspace, explica o periodo de 7 dias e mostra claramente os primeiros passos.',
    },
    'How the Trial Works': {'es': 'Como funciona la prueba', 'pt': 'Como o teste funciona'},
    '4 Steps': {'es': '4 pasos', 'pt': '4 passos'},
    '1. Review the workspace': {'es': '1. Revisa el workspace', 'pt': '1. Revise o workspace'},
    'Start with the overview, tutorial, and pricing so the offer feels clear before you create anything.': {'es': 'Empieza con la vista general, el tutorial y los precios para que la oferta quede clara antes de crear nada.', 'pt': 'Comece pela visao geral, tutorial e precos para que a oferta fique clara antes de criar qualquer coisa.'},
    '2. Create secure access': {'es': '2. Crea acceso seguro', 'pt': '2. Crie acesso seguro'},
    'Create the business owner login for {business_name} and open the Welcome Center.': {'es': 'Crea el acceso del propietario para {business_name} y abre el Centro de Bienvenida.', 'pt': 'Crie o login do proprietario para {business_name} e abra o Centro de Boas-Vindas.'},
    '3. Choose your subscription': {'es': '3. Elige tu suscripcion', 'pt': '3. Escolha sua assinatura'},
    'Select the tier that fits your business now, with full pricing visible and no pressure to enter billing today.': {'es': 'Selecciona el nivel que mejor encaje con tu negocio, con precios visibles y sin presion para agregar cobro hoy.', 'pt': 'Selecione o nivel que melhor atende sua empresa, com os precos visiveis e sem pressao para adicionar cobranca hoje.'},
    '4. Continue the free trial': {'es': '4. Continua la prueba gratis', 'pt': '4. Continue o teste gratis'},
    'Enter business details, explore the workspace, and upgrade later before the complimentary period ends.': {'es': 'Ingresa los datos del negocio, explora el workspace y mejora despues antes de que termine el periodo gratuito.', 'pt': 'Informe os dados da empresa, explore o workspace e faca upgrade depois antes do fim do periodo gratuito.'},
    'Choose your growth path now': {'es': 'Elige ahora tu camino de crecimiento', 'pt': 'Escolha agora seu caminho de crescimento'},
    'Each tier opens separately so the pricing stays visible first and the details stay organized.': {'es': 'Cada nivel se abre por separado para que el precio quede visible primero y los detalles se mantengan organizados.', 'pt': 'Cada nivel abre separadamente para que o preco fique visivel primeiro e os detalhes continuem organizados.'},
    'Subscription Options': {'es': 'Opciones de suscripcion', 'pt': 'Opcoes de assinatura'},
    'Coming Soon:': {'es': 'Proximamente:', 'pt': 'Em breve:'},
    'Claim Trial & Create Login': {'es': 'Activa la prueba y crea tu acceso', 'pt': 'Ative o teste e crie seu login'},
    'Continue with the free trial now': {'es': 'Continua con la prueba gratis ahora', 'pt': 'Continue com o teste gratis agora'},
    'The trial workspace opens first. Billing can be added later before the complimentary period ends.': {'es': 'El workspace de prueba se abre primero. La facturacion puede agregarse despues antes de que termine el periodo gratuito.', 'pt': 'O workspace de teste abre primeiro. A cobranca pode ser adicionada depois antes do fim do periodo gratuito.'},
    'Trial Offer': {'es': 'Oferta de prueba', 'pt': 'Oferta de teste'},
    '{trial_offer_days} complimentary days': {'es': '{trial_offer_days} dias gratuitos', 'pt': '{trial_offer_days} dias gratuitos'},
    'After Login': {'es': 'Despues del acceso', 'pt': 'Depois do login'},
    'Welcome Center first, then quick setup': {'es': 'Centro de Bienvenida primero y luego configuracion rapida', 'pt': 'Centro de Boas-Vindas primeiro e depois configuracao rapida'},
    'Create Password': {'es': 'Crear contraseña', 'pt': 'Criar senha'},
    'Continue with Free Trial': {'es': 'Continuar con la prueba gratis', 'pt': 'Continuar com o teste gratis'},
    'No payment required today.': {'es': 'No se requiere pago hoy.', 'pt': 'Nenhum pagamento e necessario hoje.'},
    'Create the login now, open the Welcome Center, and complete the quick setup when you are ready. You can upgrade and add billing later before the complimentary period ends.': {
        'es': 'Crea el acceso ahora, abre el Centro de Bienvenida y completa la configuracion rapida cuando estes listo. Puedes mejorar y agregar facturacion despues antes de que termine el periodo gratuito.',
        'pt': 'Crie o login agora, abra o Centro de Boas-Vindas e conclua a configuracao rapida quando estiver pronto. Voce pode fazer upgrade e adicionar cobranca depois antes do fim do periodo gratuito.',
    },
    'This business login has already been created. Sign in with the email you used for setup.': {'es': 'Este acceso empresarial ya fue creado. Inicia sesion con el correo usado en la configuracion.', 'pt': 'Este login empresarial ja foi criado. Entre com o email usado na configuracao.'},
    'This invite is no longer available.': {'es': 'Esta invitacion ya no esta disponible.', 'pt': 'Este convite nao esta mais disponivel.'},
    'Your administrator has invited you to begin secure access setup for this LedgerFlow workspace.': {'es': 'Tu administrador te invito a comenzar la configuracion de acceso seguro para este workspace LedgerFlow.', 'pt': 'Seu administrador convidou voce para iniciar a configuracao de acesso seguro deste workspace LedgerFlow.'},
    'Invite expires {expires_at}.': {'es': 'La invitacion expira {expires_at}.', 'pt': 'O convite expira em {expires_at}.'},
    'Next Step': {'es': 'Siguiente paso', 'pt': 'Proximo passo'},
    'Create login and continue to setup': {'es': 'Crea el acceso y continua con la configuracion', 'pt': 'Crie o login e continue para a configuracao'},
    'This invite creates your login first. It does not open the full workspace until setup is completed.': {'es': 'Esta invitacion crea primero tu acceso. No abre el workspace completo hasta que la configuracion este terminada.', 'pt': 'Este convite cria primeiro o seu login. Ele nao abre o workspace completo ate a configuracao ser concluida.'},
    'Business Access': {'es': 'Acceso empresarial', 'pt': 'Acesso empresarial'},
    'Invite Email': {'es': 'Email de invitacion', 'pt': 'Email de convite'},
    'Billing Center': {'es': 'Central de facturacion', 'pt': 'Central de faturamento'},
    'Payroll Tax': {'es': 'Impuesto de nomina', 'pt': 'Imposto da folha'},
    'Enter your email and submit a reset request. If your account exists, LedgerFlow will process the request safely.': {
        'es': 'Ingresa tu correo y envia una solicitud de restablecimiento. Si tu cuenta existe, LedgerFlow procesara la solicitud de forma segura.',
        'pt': 'Digite seu email e envie uma solicitacao de redefinicao. Se sua conta existir, o LedgerFlow vai processar a solicitacao com seguranca.',
    },
})


def business_color(client_id: int | None) -> str:
    if not client_id:
        return '#2563eb'
    return BUSINESS_COLORS[(int(client_id) - 1) % len(BUSINESS_COLORS)]


def normalize_language(value: str | None) -> str:
    code = (value or '').strip().lower()
    supported = {item[0] for item in LANGUAGE_OPTIONS}
    return code if code in supported else 'en'


def language_options():
    return [{'code': code, 'label': label} for code, label in LANGUAGE_OPTIONS]


def translate_text(text: str, lang: str = 'en', **kwargs) -> str:
    source = str(text or '')
    candidates = [source]
    stripped = source.strip()
    normalized_whitespace = re.sub(r'\s+', ' ', stripped)
    for candidate in (stripped, normalized_whitespace):
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    translated = None
    for candidate in candidates:
        translated = TRANSLATIONS.get(candidate, {}).get(normalize_language(lang))
        if translated is not None:
            break
    if translated is None:
        translated = source
    if kwargs:
        try:
            return translated.format(**kwargs)
        except Exception:
            return translated
    return translated


def _normalize_address(address: str) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', (address or '').lower()).strip()


KNOWN_COORDS = {
    _normalize_address(RDS_ADDRESS): (27.26955, -82.51072),
    _normalize_address('2373 Achilles St, Port Charlotte, FL 33953'): (27.01405, -82.21535),
    _normalize_address('10901 Roosevelt Blvd N Bldg 2, Saint Petersburg, FL 33716'): (27.87082, -82.67125),
}


@lru_cache(maxsize=256)
def geocode_address(address: str):
    normalized = _normalize_address(address)
    if normalized in KNOWN_COORDS:
        lat, lon = KNOWN_COORDS[normalized]
        return type('Point', (), {'latitude': lat, 'longitude': lon})()
    if '3934 brookside' in normalized and 'sarasota' in normalized:
        lat, lon = KNOWN_COORDS[_normalize_address(RDS_ADDRESS)]
        return type('Point', (), {'latitude': lat, 'longitude': lon})()
    geolocator = Nominatim(user_agent='cpa_master_pro_web')
    try:
        return geolocator.geocode(address, timeout=10)
    except Exception:
        return None


def estimate_miles(from_address: str, to_address: str) -> float:
    if not (from_address and to_address):
        return 0.0
    start = geocode_address(from_address)
    end = geocode_address(to_address)
    if not start or not end:
        return 0.0
    straight_miles = geodesic((start.latitude, start.longitude), (end.latitude, end.longitude)).miles
    return round(straight_miles * ROAD_FACTOR, 2)


def money(value: float | int | Decimal) -> float:
    return float(Decimal(str(value or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def upsert_customer_contact(
    conn: sqlite3.Connection,
    client_id: int,
    customer_name: str,
    customer_email: str = '',
    customer_phone: str = '',
    customer_address: str = '',
    customer_notes: str = '',
    created_by_user_id: int | None = None,
):
    name = (customer_name or '').strip()
    if not name:
        return None
    email = (customer_email or '').strip().lower()
    phone = (customer_phone or '').strip()
    address = (customer_address or '').strip()
    notes = (customer_notes or '').strip()
    matched = None
    if email:
        matched = conn.execute(
            '''SELECT *
               FROM customer_contacts
               WHERE client_id=?
                 AND LOWER(COALESCE(customer_email,''))=?
               LIMIT 1''',
            (client_id, email),
        ).fetchone()
    if not matched:
        matched = conn.execute(
            '''SELECT *
               FROM customer_contacts
               WHERE client_id=?
                 AND LOWER(TRIM(customer_name))=?
               ORDER BY CASE WHEN COALESCE(customer_email,'')='' THEN 0 ELSE 1 END, id DESC
               LIMIT 1''',
            (client_id, name.lower()),
        ).fetchone()
    timestamp = now_iso()
    if matched:
        merged_email = email or (matched['customer_email'] or '')
        merged_phone = phone or (matched['customer_phone'] or '')
        merged_address = address or (matched['customer_address'] or '')
        merged_notes = notes or (matched['customer_notes'] or '')
        conn.execute(
            '''UPDATE customer_contacts
               SET customer_name=?,
                   customer_email=?,
                   customer_phone=?,
                   customer_address=?,
                   customer_notes=?,
                   status='active',
                   updated_at=?,
                   updated_by_user_id=?
               WHERE id=?''',
            (
                name,
                merged_email,
                merged_phone,
                merged_address,
                merged_notes,
                timestamp,
                created_by_user_id,
                matched['id'],
            ),
        )
        return matched['id']
    cursor = conn.execute(
        '''INSERT INTO customer_contacts (
               client_id, customer_name, customer_email, customer_phone, customer_address,
               customer_notes, status, created_by_user_id, updated_by_user_id, created_at, updated_at
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
        (
            client_id,
            name,
            email,
            phone,
            address,
            notes,
            'active',
            created_by_user_id,
            created_by_user_id,
            timestamp,
            timestamp,
        ),
    )
    return cursor.lastrowid


def customer_contact_dependency_summary(conn: sqlite3.Connection, client_id: int, contact_id: int) -> dict:
    contact = conn.execute(
        'SELECT * FROM customer_contacts WHERE id=? AND client_id=?',
        (contact_id, client_id),
    ).fetchone()
    contact_name = ((contact['customer_name'] if contact else '') or '').strip().lower()
    contact_email = ((contact['customer_email'] if contact else '') or '').strip().lower()
    work_schedule_count = conn.execute(
        'SELECT COUNT(*) n FROM work_schedule_entries WHERE client_id=? AND customer_contact_id=?',
        (client_id, contact_id),
    ).fetchone()['n']
    job_count = conn.execute(
        'SELECT COUNT(*) n FROM jobs WHERE client_id=? AND customer_contact_id=?',
        (client_id, contact_id),
    ).fetchone()['n']
    location_count = conn.execute(
        'SELECT COUNT(*) n FROM service_locations WHERE client_id=? AND customer_contact_id=?',
        (client_id, contact_id),
    ).fetchone()['n']
    if contact_email:
        estimate_count = conn.execute(
            """SELECT COUNT(*) n
               FROM invoices
               WHERE client_id=?
                 AND COALESCE(record_kind,'')='estimate'
                 AND (
                   customer_contact_id=?
                   OR (
                     customer_contact_id IS NULL
                     AND LOWER(TRIM(COALESCE(client_name,'')))=?
                     AND LOWER(TRIM(COALESCE(recipient_email,'')))=?
                   )
                 )""",
            (client_id, contact_id, contact_name, contact_email),
        ).fetchone()['n']
        invoice_count = conn.execute(
            """SELECT COUNT(*) n
               FROM invoices
               WHERE client_id=?
                 AND COALESCE(record_kind,'')='customer_invoice'
                 AND (
                   customer_contact_id=?
                   OR (
                     customer_contact_id IS NULL
                     AND LOWER(TRIM(COALESCE(client_name,'')))=?
                     AND LOWER(TRIM(COALESCE(recipient_email,'')))=?
                   )
                 )""",
            (client_id, contact_id, contact_name, contact_email),
        ).fetchone()['n']
    else:
        estimate_count = conn.execute(
            """SELECT COUNT(*) n
               FROM invoices
               WHERE client_id=?
                 AND COALESCE(record_kind,'')='estimate'
                 AND (
                   customer_contact_id=?
                   OR (
                     customer_contact_id IS NULL
                     AND LOWER(TRIM(COALESCE(client_name,'')))=?
                   )
                 )""",
            (client_id, contact_id, contact_name),
        ).fetchone()['n']
        invoice_count = conn.execute(
            """SELECT COUNT(*) n
               FROM invoices
               WHERE client_id=?
                 AND COALESCE(record_kind,'')='customer_invoice'
                 AND (
                   customer_contact_id=?
                   OR (
                     customer_contact_id IS NULL
                     AND LOWER(TRIM(COALESCE(client_name,'')))=?
                   )
                 )""",
            (client_id, contact_id, contact_name),
        ).fetchone()['n']
    total_links = int(work_schedule_count or 0) + int(job_count or 0) + int(location_count or 0) + int(estimate_count or 0) + int(invoice_count or 0)
    return {
        'work_schedule_count': int(work_schedule_count or 0),
        'job_count': int(job_count or 0),
        'location_count': int(location_count or 0),
        'estimate_count': int(estimate_count or 0),
        'invoice_count': int(invoice_count or 0),
        'total_links': total_links,
        'can_delete': total_links == 0,
    }


def recurring_frequency_options():
    return [
        ('', 'One-time / no repeat'),
        ('weekly', 'Weekly'),
        ('biweekly', 'Every 2 Weeks'),
        ('monthly', 'Monthly'),
    ]


def recurring_weekday_options():
    return [(str(i), day) for i, day in enumerate(['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'])]


def projected_recurring_monthly_amount(contact) -> float:
    amount = money((contact['recurring_expected_amount'] if 'recurring_expected_amount' in contact.keys() else 0) or 0)
    frequency = ((contact['recurring_frequency'] if 'recurring_frequency' in contact.keys() else '') or '').strip().lower()
    if amount <= 0:
        return 0.0
    if frequency == 'weekly':
        return money(amount * 4.33)
    if frequency == 'biweekly':
        return money(amount * 2.17)
    if frequency == 'monthly':
        return money(amount)
    return 0.0


def recurring_occurrence_dates(contact, window_start: date | None = None, horizon_days: int = 42, limit: int = 18):
    frequency = ((contact['recurring_frequency'] if 'recurring_frequency' in contact.keys() else '') or '').strip().lower()
    if frequency not in {'weekly', 'biweekly', 'monthly'}:
        return []
    start_date = parse_date((contact['recurring_start_date'] if 'recurring_start_date' in contact.keys() else '') or '') or date.today()
    end_date = parse_date((contact['recurring_end_date'] if 'recurring_end_date' in contact.keys() else '') or '')
    window_start = max(window_start or date.today(), start_date)
    horizon_end = window_start + timedelta(days=max(horizon_days, 1))
    if end_date and end_date < window_start:
        return []

    results: list[date] = []
    if frequency in {'weekly', 'biweekly'}:
        weekday_value = str((contact['recurring_weekday'] if 'recurring_weekday' in contact.keys() else '') or '').strip()
        target_weekday = int(weekday_value) if weekday_value.isdigit() else start_date.weekday()
        anchor = start_date
        if anchor.weekday() != target_weekday:
            anchor = anchor + timedelta(days=(target_weekday - anchor.weekday()) % 7)
        current = window_start + timedelta(days=(target_weekday - window_start.weekday()) % 7)
        step_days = 7
        while current <= horizon_end and len(results) < limit:
            if current >= anchor:
                weeks_between = (current - anchor).days // 7
                if frequency == 'weekly' or weeks_between % 2 == 0:
                    if not end_date or current <= end_date:
                        results.append(current)
            current += timedelta(days=step_days)
    else:
        import calendar as pycal
        target_day = start_date.day
        current_month = date(window_start.year, window_start.month, 1)
        while current_month <= horizon_end and len(results) < limit:
            last_day = pycal.monthrange(current_month.year, current_month.month)[1]
            candidate = date(current_month.year, current_month.month, min(target_day, last_day))
            if candidate >= window_start and candidate >= start_date and (not end_date or candidate <= end_date):
                results.append(candidate)
            if current_month.month == 12:
                current_month = date(current_month.year + 1, 1, 1)
            else:
                current_month = date(current_month.year, current_month.month + 1, 1)
    return results


def ensure_recurring_schedule_entries(conn: sqlite3.Connection, client_id: int, actor_user_id: int | None = None, horizon_days: int = 42) -> int:
    today = date.today()
    contact_rows = conn.execute(
        '''SELECT *
           FROM customer_contacts
           WHERE client_id=?
             AND COALESCE(status,'active')='active'
             AND COALESCE(auto_add_to_calendar,0)=1
             AND COALESCE(recurring_frequency,'')<>''',
        (client_id,),
    ).fetchall()
    created_count = 0
    for row in contact_rows:
        expected_amount = money(row['recurring_expected_amount'] or 0)
        job_name = ((row['recurring_job_name'] or '').strip() or (row['customer_name'] or '').strip() or 'Recurring Service').strip()
        scope = ((row['recurring_scope'] or '').strip() or (row['customer_notes'] or '').strip())
        note_parts = ['Generated from recurring client profile.']
        if expected_amount > 0:
            note_parts.append(f'Expected amount ${expected_amount:.2f}')
        notes = ' '.join(note_parts).strip()
        for occurrence in recurring_occurrence_dates(row, window_start=today, horizon_days=horizon_days):
            existing = conn.execute(
                '''SELECT id
                   FROM work_schedule_entries
                   WHERE client_id=?
                     AND customer_contact_id=?
                     AND schedule_date=?
                     AND COALESCE(auto_generated,0)=1
                   LIMIT 1''',
                (client_id, row['id'], occurrence.isoformat()),
            ).fetchone()
            if existing:
                continue
            conn.execute(
                '''INSERT INTO work_schedule_entries (
                    client_id, customer_contact_id, job_name, job_address, scope_of_work, schedule_date,
                    start_time, end_time, estimated_duration, assigned_worker_ids, assigned_worker_names,
                    notes, created_by_user_id, auto_generated, expected_amount
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (
                    client_id,
                    row['id'],
                    job_name,
                    (row['customer_address'] or '').strip(),
                    scope,
                    occurrence.isoformat(),
                    (row['recurring_start_time'] or '').strip(),
                    (row['recurring_end_time'] or '').strip(),
                    (row['recurring_estimated_duration'] or '').strip(),
                    '',
                    '',
                    notes,
                    actor_user_id,
                    1,
                    expected_amount,
                ),
            )
            created_count += 1
    return created_count


def clean_last4(value: str) -> str:
    digits = re.sub(r'\D+', '', value or '')
    return digits[-4:] if digits else ''


def clean_digits(value: str) -> str:
    return re.sub(r'\D+', '', value or '')


def mask_account_number(value: str, visible_digits: int = 4, min_mask: int = 4) -> str:
    digits = clean_digits(value)
    if not digits:
        return ''
    visible = digits[-visible_digits:] if len(digits) > visible_digits else digits
    return ('*' * max(min_mask, len(digits) - len(visible))) + visible


def mask_card_number(value: str) -> str:
    digits = clean_digits(value)
    if not digits:
        return ''
    visible = digits[-4:] if len(digits) > 4 else digits
    masked = ('*' * max(12, len(digits) - len(visible))) + visible
    groups = [masked[i:i+4] for i in range(0, len(masked), 4)]
    return ' '.join(groups)


def business_structures():
    return ['LLC', 'S-Corp', 'C-Corp', 'Sole Proprietor', 'Partnership', 'Nonprofit', 'Other']


def business_types():
    return business_structures()


def business_categories():
    return [
        'Cleaning',
        'Painting',
        'Nails / Beauty',
        'Massage / Wellness',
        'Construction',
        'Landscaping',
        'Floor Installation',
        'Mobile Detailing',
        'Home Services',
        'Childcare',
        'Consulting',
        'Bookkeeping / Accounting',
        'Retail / Boutique',
        'Food / Catering',
        'Fitness / Personal Training',
        'Other',
    ]


def normalize_business_category(value: str) -> str:
    cleaned = (value or '').strip()
    if not cleaned:
        return ''
    return cleaned if cleaned in set(business_categories()) else 'Other'


def normalize_email_address(value: str) -> str:
    _display_name, address = parseaddr((value or '').strip())
    cleaned = (address or '').strip().lower()
    if not cleaned or ' ' in cleaned or cleaned.count('@') != 1:
        return ''
    local_part, domain_part = cleaned.split('@', 1)
    if not local_part or not domain_part or domain_part.startswith('.') or domain_part.endswith('.') or '.' not in domain_part:
        return ''
    return cleaned


def resolve_invite_recipient_email(invited_email: str, client_email: str = '') -> tuple[str, str]:
    normalized_invited_email = normalize_email_address(invited_email)
    if normalized_invited_email:
        return normalized_invited_email, ''
    normalized_client_email = normalize_email_address(client_email)
    if normalized_client_email:
        return normalized_client_email, 'Saved invite email was invalid, so LedgerFlow used the business email on file instead.'
    return '', 'Saved invite email is invalid. Update the business email first.'


def business_category_display(value: str) -> str:
    normalized = normalize_business_category(value)
    return normalized or 'Service Business'


def prospect_visual_profile(category: str) -> dict:
    normalized = normalize_business_category(category)
    profiles = {
        'Cleaning': {
            'filename': 'marketing/prospect-cleaning.png',
            'alt': 'LedgerFlow preview for cleaning businesses',
            'headline': 'Keep recurring cleanings, billing, and cash flow organized.',
            'invite_points': [
                'See how recurring cleanings can stay visible without chasing spreadsheets.',
                'Review the full pricing clearly and begin the trial with no card required.',
                'Open a cleaner onboarding path with guided setup and direct administrator support.',
            ],
            'followup_points': [
                'Recurring visits, billing, and profit visibility can start feeling organized right away.',
                'Your team, schedule, and paid-vs-open work can stay in one calm workspace.',
                'The complimentary trial lets you explore all of that before billing is added later.',
            ],
        },
        'Painting': {
            'filename': 'marketing/prospect-painting.png',
            'alt': 'LedgerFlow preview for painting businesses',
            'headline': 'Keep estimates, invoices, and cash flow under control.',
            'invite_points': [
                'Review the estimate-to-invoice flow and cleaner payment visibility before you decide.',
                'Open the complimentary trial now and choose a subscription later with full pricing visible.',
                'Use the guided setup to see how LedgerFlow can support project-based service work.',
            ],
            'followup_points': [
                'Project pricing, invoice follow-up, and open-balance visibility are waiting inside the trial.',
                'You can review business billing, schedule coordination, and reports without adding a card today.',
                'If the first message was buried, this follow-up is the faster path back into your private trial.',
            ],
        },
    }
    default_profile = {
        'filename': 'marketing/prospect-service-generic.png',
        'alt': 'LedgerFlow preview for growing service businesses',
        'headline': 'See how LedgerFlow can organize your service business in one workspace.',
        'invite_points': [
            'Review the guided setup, subscription options, and workspace overview before you decide.',
            'Open the complimentary trial now with no card required and pricing visible from the start.',
            'See a calmer way to manage billing, scheduling, and reports with direct administrator support.',
        ],
        'followup_points': [
            'Billing, scheduling, reports, and client-facing workflow are all waiting inside the trial experience.',
            'You can explore the workspace first and add billing later only if LedgerFlow feels right for your business.',
            'If the first email was buried in Promotions or Spam, this follow-up gives you the short path back in.',
        ],
    }
    return profiles.get(normalized, default_profile)


def filing_types():
    return ['1099', 'W-2', 'Both']


def eftps_statuses():
    return ['Not Enrolled', 'Pending', 'Enrolled']


def subscription_tier_catalog():
    return [
        {
            'key': 'self_service',
            'label': 'Essential',
            'plan_code': 'essential-client-monthly',
            'monthly_amount': Decimal('59.00'),
            'tagline': 'Private client workspace for owner-led service businesses that need clean billing, records, and calendar visibility.',
            'best_for': 'Best for smaller direct-admin client accounts.',
            'features': [
                'Business workspace dashboard',
                'Billing center with method on file',
                'Income records and expense tracking',
                'Calendar and work schedule access',
                'Direct administrator support',
            ],
            'coming_soon': [],
        },
        {
            'key': 'assisted_service',
            'label': 'Growth',
            'plan_code': 'growth-client-monthly',
            'monthly_amount': Decimal('99.00'),
            'tagline': 'Adds team tools and stronger operational support for growing businesses with active payroll coordination.',
            'best_for': 'Best for businesses managing staff and payroll visibility.',
            'features': [
                'Everything in Essential',
                'Team member portal access',
                'Team member payouts and pay stubs',
                'Policies, notices, and requests',
                'Expanded administrator guidance',
            ],
            'coming_soon': [],
        },
        {
            'key': 'premium_principal',
            'label': 'Premium',
            'plan_code': 'premium-client-monthly',
            'monthly_amount': Decimal('149.00'),
            'tagline': 'Highest-touch private client tier with premium onboarding, priority support, and principal-level oversight.',
            'best_for': 'Best for clients who want concierge support and deeper administrator involvement.',
            'features': [
                'Everything in Growth',
                'Priority support response',
                'Premium onboarding review',
                'Principal-level workspace oversight',
                'Higher-touch billing coordination',
            ],
            'coming_soon': [
                'Live bank connection',
                'Check printing workflow',
            ],
        },
    ]


def subscription_tier_details_map():
    return {item['key']: item for item in subscription_tier_catalog()}


def subscription_tier_view_data():
    return [
        {
            **item,
            'monthly_amount': float(item['monthly_amount']),
        }
        for item in subscription_tier_catalog()
    ]


def subscription_tier_view_map():
    return {item['key']: item for item in subscription_tier_view_data()}


def service_level_options():
    return [(item['key'], item['label']) for item in subscription_tier_catalog()]


def service_level_label_map():
    return dict(service_level_options())


def service_level_access_options():
    return [('', 'Match pricing tier')] + service_level_options()


def default_service_level() -> str:
    return 'self_service'


def normalize_service_level(value: str) -> str:
    allowed = {key for key, _ in service_level_options()}
    cleaned = (value or '').strip().lower()
    return cleaned if cleaned in allowed else default_service_level()


def normalize_access_service_level(value: str) -> str:
    cleaned = (value or '').strip().lower()
    if not cleaned:
        return ''
    return normalize_service_level(cleaned)


def row_value(row, key: str, default=''):
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def effective_service_level(client_row) -> str:
    override_level = normalize_access_service_level(row_value(client_row, 'access_service_level', ''))
    if override_level:
        return override_level
    return normalize_service_level(row_value(client_row, 'service_level', default_service_level()))


def access_level_override_active(client_row) -> bool:
    override_level = normalize_access_service_level(row_value(client_row, 'access_service_level', ''))
    billed_level = normalize_service_level(row_value(client_row, 'service_level', default_service_level()))
    return bool(override_level and override_level != billed_level)


def effective_service_level_label(client_row) -> str:
    level = effective_service_level(client_row)
    return service_level_label_map().get(level, service_level_label_map().get(default_service_level(), 'Essential'))


def premium_sales_access_enabled(client_row) -> bool:
    return effective_service_level(client_row) == 'premium_principal'


def premium_sales_redirect(client_id: int):
    flash('Clients, estimates, and customer invoicing are available on the Premium subscription.', 'error')
    return redirect(url_for('business_payments_page', client_id=client_id))


def service_level_plan_code(service_level: str) -> str:
    normalized = normalize_service_level(service_level)
    return subscription_tier_details_map().get(normalized, subscription_tier_details_map()[default_service_level()])['plan_code']


def default_trial_offer_days() -> int:
    return 7


def normalize_invite_kind(value: str) -> str:
    cleaned = (value or '').strip().lower()
    return cleaned if cleaned in {'business_access', 'prospect_trial'} else 'business_access'


def invite_kind_label(value: str) -> str:
    return {
        'business_access': 'Business Access Invite',
        'prospect_trial': f'{default_trial_offer_days()}-Day Trial Invite',
    }.get(normalize_invite_kind(value), 'Business Access Invite')


def tracked_email_click_link(tracking_token: str, target_url: str) -> str:
    safe_target = (target_url or '').strip()
    if not safe_target or not tracking_token:
        return safe_target
    return public_app_url(f"/email/click/{tracking_token}?{urlencode({'target': safe_target})}")


def email_tracking_pixel_url(tracking_token: str) -> str:
    if not tracking_token:
        return ''
    return public_app_url(f'/email/open/{tracking_token}.gif')


def prospect_visual_card_html(business_category: str, business_name: str) -> str:
    profile = prospect_visual_profile(business_category)
    image_url = html.escape(static_asset_absolute_url(profile['filename']))
    alt_text = html.escape(profile['alt'])
    category_label = html.escape(business_category_display(business_category))
    business_label = html.escape((business_name or 'Your business').strip() or 'Your business')
    return (
        f"<div style='margin-top:22px;padding:18px;border:1px solid #dbe3ef;border-radius:22px;background:#ffffff'>"
        f"<img src='{image_url}' alt='{alt_text}' style='display:block;width:100%;height:auto;border-radius:16px'>"
        f"<div style='margin-top:14px;color:#151a2c;font-size:18px;line-height:1.35;font-weight:800'>{html.escape(profile['headline'])}</div>"
        f"<div style='margin-top:8px;color:#61718a;font-size:13px;line-height:1.7'>{business_label} is currently being invited as a <strong style='color:#1d2336'>{category_label}</strong> business.</div>"
        f"</div>"
    )


def trial_subscription_preview_html() -> str:
    tier_rows = []
    for tier in subscription_tier_catalog():
        feature_preview = ', '.join(tier['features'][:3])
        coming_soon = ''
        if tier.get('coming_soon'):
            coming_soon = (
                f"<div style='margin-top:6px;color:#7f5f1d;font-size:12px;line-height:1.6'><strong>Coming Soon:</strong> "
                f"{html.escape(', '.join(tier['coming_soon']))}</div>"
            )
        tier_rows.append(
            f"<tr>"
            f"<td style='padding:14px 12px;border-bottom:1px solid #e3e7ee;color:#16314f;font-size:14px;font-weight:800'>{html.escape(tier['label'])}</td>"
            f"<td style='padding:14px 12px;border-bottom:1px solid #e3e7ee;color:#16314f;font-size:14px;font-weight:800'>${float(tier['monthly_amount']):.0f}/mo</td>"
            f"<td style='padding:14px 12px;border-bottom:1px solid #e3e7ee;color:#4b5e79;font-size:13px;line-height:1.6'>{html.escape(tier['best_for'])}<br>{html.escape(feature_preview)}{coming_soon}</td>"
            f"</tr>"
        )
    return (
        f"<div style='margin-top:18px;padding:18px 20px;border:1px solid #dbe3ef;border-radius:18px;background:#ffffff'>"
        f"<div style='color:#141b2d;font-size:14px;font-weight:800;margin-bottom:12px'>Subscription options preview</div>"
        f"<table role='presentation' style='width:100%;border-collapse:collapse'>"
        f"<tr><th align='left' style='padding:0 12px 10px 12px;color:#74829b;font-size:12px;letter-spacing:.08em;text-transform:uppercase'>Tier</th><th align='left' style='padding:0 12px 10px 12px;color:#74829b;font-size:12px;letter-spacing:.08em;text-transform:uppercase'>Price</th><th align='left' style='padding:0 12px 10px 12px;color:#74829b;font-size:12px;letter-spacing:.08em;text-transform:uppercase'>Designed For</th></tr>"
        f"{''.join(tier_rows)}"
        f"</table>"
        f"</div>"
    )


def trial_offer_value_stack_html(*, business_category: str, trial_days: int, stronger: bool = False) -> str:
    profile = prospect_visual_profile(business_category)
    point_source = profile['followup_points'] if stronger else profile['invite_points']
    points_html = ''.join(
        f"<li style='margin:0 0 10px;color:#4a576d;font-size:14px;line-height:1.7'>{html.escape(point)}</li>"
        for point in point_source
    )
    intro_label = 'What you are missing inside the trial' if stronger else 'What the trial includes'
    intro_copy = (
        'No open signal was recorded after 3 days, so this follow-up is designed to show the value faster. '
        'That can happen when a first email gets buried in an inbox tab, Promotions, or Spam, but SMTP cannot confirm the exact folder.'
        if stronger else
        'Review the subscription options below, create your secure login, and complete setup when you are ready. Billing begins only after the complimentary trial window ends.'
    )
    return (
        f"<div style='margin-top:22px;padding:18px 20px;border:1px solid #d7dce7;border-radius:18px;background:#f7f1e7'>"
        f"<div style='color:#141b2d;font-size:13px;font-weight:800;letter-spacing:.08em;text-transform:uppercase'>Complimentary Trial Offer</div>"
        f"<div style='margin-top:8px;color:#141b2d;font-size:24px;line-height:1.25;font-weight:800'>{trial_days}-day free guided trial</div>"
        f"<div style='margin-top:10px;color:#48546a;font-size:14px;line-height:1.7'>{html.escape(intro_copy)}</div>"
        f"</div>"
        f"<div style='margin-top:18px;padding:18px 20px;border:1px solid #dbe3ef;border-radius:18px;background:#ffffff'>"
        f"<div style='color:#141b2d;font-size:14px;font-weight:800;margin-bottom:12px'>{html.escape(intro_label)}</div>"
        f"<ul style='margin:0;padding-left:18px'>{points_html}</ul>"
        f"</div>"
        f"{trial_subscription_preview_html()}"
    )


def trial_date_window(started_at: str, trial_days: int) -> tuple[str, str]:
    base = datetime.utcnow()
    if started_at:
        try:
            base = datetime.fromisoformat(started_at.replace('Z', '+00:00')).replace(tzinfo=None)
        except ValueError:
            try:
                base = datetime.strptime(started_at[:19], '%Y-%m-%dT%H:%M:%S')
            except ValueError:
                try:
                    base = datetime.strptime(started_at[:19], '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    base = datetime.utcnow()
    if trial_days <= 0:
        trial_days = default_trial_offer_days()
    end = base + timedelta(days=trial_days)
    return base.isoformat(timespec='seconds'), end.isoformat(timespec='seconds')


def business_archive_reason_options():
    return [
        ('business_canceled', 'Business Canceled'),
        ('business_dismissed', 'Business Dismissed'),
        ('business_closed', 'Business Closed'),
        ('duplicate_record', 'Duplicate Record'),
        ('other', 'Other'),
    ]


def business_archive_reason_label_map():
    return dict(business_archive_reason_options())


def normalize_business_archive_reason(value: str) -> str:
    allowed = {key for key, _ in business_archive_reason_options()}
    cleaned = (value or '').strip().lower()
    return cleaned if cleaned in allowed else 'other'


def prospect_pipeline_stage(row) -> dict:
    invite_kind = normalize_invite_kind(row['invite_kind'])
    invite_status = (row['invite_status'] or '').strip().lower()
    followup_status = (row_value(row, 'followup_status', '') or '').strip().lower()
    onboarding_status = (row['onboarding_status'] or 'completed').strip().lower()
    accepted_user_id = row['invite_accepted_user_id']
    trial_days = int(row['trial_days'] or row['trial_offer_days'] or 0)
    is_trial = invite_kind == 'prospect_trial' and trial_days > 0

    if invite_status == 'failed':
        return {
            'key': 'delivery_failed',
            'label': 'Trial Invite Failed' if is_trial else 'Delivery Failed',
            'detail': (
                f'The {trial_days}-day trial email did not deliver. Review the issue or resend the invite.'
                if is_trial else
                'Email delivery failed. Review the issue or resend the invite.'
            ),
        }
    if invite_status == 'expired':
        return {
            'key': 'invite_expired',
            'label': 'Trial Offer Expired' if is_trial else 'Invite Expired',
            'detail': (
                'The complimentary trial offer expired before secure login setup was completed.'
                if is_trial else
                'The invite link expired before login setup was completed.'
            ),
        }
    if accepted_user_id and onboarding_status == 'in_progress':
        return {
            'key': 'setup_in_progress',
            'label': 'Trial Setup In Progress' if is_trial else 'Setup In Progress',
            'detail': (
                f'The {trial_days}-day trial was claimed and LedgerFlow setup is underway.'
                if is_trial else
                'The business login exists and setup has started, but onboarding is not finished yet.'
            ),
        }
    if accepted_user_id:
        return {
            'key': 'login_created',
            'label': 'Trial Claimed' if is_trial else 'Login Created',
            'detail': (
                f'The business claimed the {trial_days}-day trial and is ready to complete setup.'
                if is_trial else
                'The business login was created and is waiting to complete LedgerFlow setup.'
            ),
        }
    if invite_status in {'sent', 'pending'}:
        return {
            'key': 'invite_sent',
            'label': 'Trial Follow-Up Sent' if is_trial and followup_status == 'sent' else 'Trial Invite Sent' if is_trial else 'Invite Sent',
            'detail': (
                'A higher-value follow-up was sent after 3 days with no open signal. LedgerFlow is now waiting for the business to open the trial and create secure access.'
                if is_trial and followup_status == 'sent' else
                f'Waiting for the business to open its {trial_days}-day complimentary trial invite and create secure access.'
                if is_trial else
                'Waiting for the business to open the invite and create its login.'
            ),
        }
    return {
        'key': 'prospect',
        'label': 'Trial Prospect' if is_trial else 'Prospect',
        'detail': (
            'Trial-ready prospect record created and waiting for the next outreach action.'
            if is_trial else
            'Prospect record created and waiting for the next outreach action.'
        ),
    }


def summarize_prospect_pipeline(rows) -> dict:
    counts = {
        'invite_sent': 0,
        'login_created': 0,
        'setup_in_progress': 0,
        'delivery_failed': 0,
        'invite_expired': 0,
        'prospect': 0,
    }
    for row in rows or []:
        stage = prospect_pipeline_stage(row)
        counts[stage['key']] = counts.get(stage['key'], 0) + 1
    return counts


def client_delete_blockers(conn: sqlite3.Connection, client_id: int) -> dict[str, int]:
    blockers: dict[str, int] = {}
    ignored_tables = {'client_profile_history', 'worker_profile_history'}
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name<>'clients'"
    ).fetchall()
    for row in tables:
        table_name = row['name']
        if table_name in ignored_tables:
            continue
        try:
            columns = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        except sqlite3.DatabaseError:
            continue
        if not any(col['name'] == 'client_id' for col in columns):
            continue
        try:
            count = conn.execute(f"SELECT COUNT(*) AS c FROM {table_name} WHERE client_id=?", (client_id,)).fetchone()['c']
        except sqlite3.DatabaseError:
            continue
        if int(count or 0) > 0:
            blockers[table_name] = int(count or 0)
    return blockers


def payment_type_options():
    return [
        ('bookkeeping', 'Bookkeeping'),
        ('extra_login_fee', 'Extra Login Fee'),
        ('assisted_service_fee', 'Assisted Service Fee'),
        ('monthly_platform_fee', 'Monthly Platform Fee'),
        ('cleanup_reconstruction', 'Cleanup / Reconstruction'),
        ('other', 'Other'),
    ]


def default_payment_type() -> str:
    return 'other'


def normalize_payment_type(value: str) -> str:
    allowed = {key for key, _ in payment_type_options()}
    cleaned = (value or '').strip().lower()
    return cleaned if cleaned in allowed else default_payment_type()


def suggested_payment_amount(service_level: str, payment_type: str) -> Decimal | None:
    tier_map = subscription_tier_details_map()
    pricing = {
        'self_service': {
            'bookkeeping': Decimal('195.00'),
            'extra_login_fee': Decimal('29.00'),
            'assisted_service_fee': Decimal('89.00'),
            'monthly_platform_fee': tier_map['self_service']['monthly_amount'],
            'cleanup_reconstruction': Decimal('350.00'),
        },
        'assisted_service': {
            'bookkeeping': Decimal('325.00'),
            'extra_login_fee': Decimal('39.00'),
            'assisted_service_fee': Decimal('129.00'),
            'monthly_platform_fee': tier_map['assisted_service']['monthly_amount'],
            'cleanup_reconstruction': Decimal('550.00'),
        },
        'premium_principal': {
            'bookkeeping': Decimal('550.00'),
            'extra_login_fee': Decimal('59.00'),
            'assisted_service_fee': Decimal('189.00'),
            'monthly_platform_fee': tier_map['premium_principal']['monthly_amount'],
            'cleanup_reconstruction': Decimal('900.00'),
        },
    }
    return pricing.get(normalize_service_level(service_level), {}).get(normalize_payment_type(payment_type))


def suggested_payment_amounts_map():
    out = {}
    for service_level, _label in service_level_options():
        out[service_level] = {}
        for payment_type, _type_label in payment_type_options():
            suggested = suggested_payment_amount(service_level, payment_type)
            out[service_level][payment_type] = float(suggested) if suggested is not None else None
    return out


def subscription_status_options():
    return [
        ('inactive', 'Inactive'),
        ('active', 'Active'),
        ('past_due', 'Past Due'),
        ('paused', 'Paused'),
        ('canceled', 'Canceled'),
    ]


def subscription_status_label_map():
    return dict(subscription_status_options())


def default_subscription_status() -> str:
    return 'inactive'


def normalize_subscription_status(value: str) -> str:
    allowed = {key for key, _ in subscription_status_options()}
    cleaned = (value or '').strip().lower()
    return cleaned if cleaned in allowed else default_subscription_status()


def collection_method_options():
    return [
        ('charge_saved_method', 'Charge Saved Payment Method'),
        ('send_payment_request', 'Send Payment Request'),
        ('send_payment_link', 'Send Payment Link / Invoice'),
        ('manual_offline', 'Manual / Offline Payment'),
        ('zelle_manual', 'Bank / Zelle Instructions'),
    ]


def collection_method_label_map():
    return dict(collection_method_options())


def default_collection_method() -> str:
    return 'send_payment_request'


def normalize_collection_method(value: str) -> str:
    allowed = {key for key, _ in collection_method_options()}
    cleaned = (value or '').strip().lower()
    return cleaned if cleaned in allowed else default_collection_method()


def payment_method_type_options():
    return [
        ('card', 'Card'),
        ('ach', 'ACH / Bank Debit'),
        ('manual_offline', 'Manual / Offline'),
        ('zelle', 'Zelle / Bank Transfer'),
        ('other', 'Other'),
    ]


def payment_method_status_options():
    return [
        ('active', 'Active'),
        ('needs_update', 'Needs Update'),
        ('inactive', 'Inactive'),
    ]


def payment_method_type_label_map():
    return dict(payment_method_type_options())


def payment_method_status_label_map():
    return dict(payment_method_status_options())


def bank_account_type_options():
    return [
        ('checking', 'Checking'),
        ('savings', 'Savings'),
    ]


def normalize_payment_method_type(value: str) -> str:
    allowed = {key for key, _ in payment_method_type_options()}
    cleaned = (value or '').strip().lower()
    return cleaned if cleaned in allowed else 'other'


def normalize_saved_method_status(value: str) -> str:
    allowed = {key for key, _ in payment_method_status_options()}
    cleaned = (value or '').strip().lower()
    return cleaned if cleaned in allowed else 'active'


def normalize_bank_account_type(value: str) -> str:
    allowed = {key for key, _ in bank_account_type_options()}
    cleaned = (value or '').strip().lower()
    return cleaned if cleaned in allowed else 'checking'


def worker_payment_method_options():
    return [
        ('direct_deposit', 'Direct Deposit / ACH'),
        ('zelle', 'Zelle / Bank Transfer'),
        ('check', 'Check'),
        ('cash', 'Cash'),
        ('other', 'Other'),
    ]


def worker_payment_status_options():
    return [
        ('scheduled', 'Scheduled'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ]


def worker_payment_method_label_map():
    return dict(worker_payment_method_options())


def worker_payment_status_label_map():
    return dict(worker_payment_status_options())


def worker_payout_preference_options():
    return [
        ('direct_deposit', 'Direct Deposit'),
        ('zelle', 'Zelle'),
        ('paper_check', 'Paper Check'),
    ]


def worker_payout_preference_label_map():
    return dict(worker_payout_preference_options())


def normalize_worker_payment_method(value: str) -> str:
    allowed = {key for key, _ in worker_payment_method_options()}
    cleaned = (value or '').strip().lower()
    return cleaned if cleaned in allowed else 'other'


def normalize_worker_payment_status(value: str) -> str:
    allowed = {key for key, _ in worker_payment_status_options()}
    cleaned = (value or '').strip().lower()
    return cleaned if cleaned in allowed else 'scheduled'


def normalize_worker_payout_preference(value: str) -> str:
    allowed = {key for key, _ in worker_payout_preference_options()}
    cleaned = (value or '').strip().lower()
    return cleaned if cleaned in allowed else 'paper_check'


def eftps_payment_url() -> str:
    return 'https://www.eftps.gov/eftps/'


def generate_invite_token() -> str:
    return secrets.token_urlsafe(24)


def payment_csrf_token() -> str:
    token = session.get('payment_csrf_token')
    if not token:
        token = secrets.token_urlsafe(32)
        session['payment_csrf_token'] = token
    return token


def valid_payment_csrf(submitted_token: str) -> bool:
    expected_token = session.get('payment_csrf_token') or ''
    return bool(submitted_token and expected_token and secrets.compare_digest(submitted_token, expected_token))


def normalize_payment_link(value: str) -> str | None:
    value = (value or '').strip()
    if not value:
        return ''
    parsed = urlparse(value)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        return None
    return value


def normalize_money_amount(value) -> Decimal | None:
    text = '' if value is None else str(value).strip()
    if not text:
        return None
    try:
        amount = Decimal(text)
    except Exception:
        return None
    return amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def payment_paid_at_for_status(status: str, existing_paid_at: str = '') -> str:
    return existing_paid_at or datetime.now().isoformat(timespec='seconds') if status == 'paid' else ''


def normalize_payment_method_status(value: str) -> str:
    cleaned = (value or '').strip().lower()
    allowed = {'missing', 'on_file', 'needs_update'}
    return cleaned if cleaned in allowed else 'missing'


def subscription_status_timestamps(status: str, existing) -> tuple[str, str, str]:
    now_value = datetime.now().isoformat(timespec='seconds')
    started_at = existing['subscription_started_at'] or ''
    canceled_at = existing['subscription_canceled_at'] or ''
    paused_at = existing['subscription_paused_at'] or ''
    if status == 'active' and not started_at:
        started_at = now_value
    if status == 'canceled':
        canceled_at = canceled_at or now_value
    else:
        canceled_at = ''
    if status == 'paused':
        paused_at = paused_at or now_value
    else:
        paused_at = ''
    return started_at, canceled_at, paused_at


def validate_subscription_profile_form(form) -> tuple[dict, list[str]]:
    errors: list[str] = []
    subscription_amount = normalize_money_amount(form.get('subscription_amount', ''))
    next_billing_raw = form.get('subscription_next_billing_date', '').strip()
    status = normalize_subscription_status(form.get('subscription_status', default_subscription_status()))
    plan_code = form.get('subscription_plan_code', '').strip()[:100]
    default_payment_method_label = form.get('default_payment_method_label', '').strip()[:120]
    backup_payment_method_label = form.get('backup_payment_method_label', '').strip()[:120]
    billing_notes = form.get('billing_notes', '').strip()[:500]
    if subscription_amount is None:
        subscription_amount = Decimal('0.00')
    if subscription_amount < 0:
        errors.append('Subscription amount cannot be negative.')
    next_billing_date = ''
    if next_billing_raw:
        parsed_next = parse_date(next_billing_raw)
        if not parsed_next:
            errors.append('Enter a valid next billing date.')
        else:
            next_billing_date = parsed_next.isoformat()
    return {
        'subscription_plan_code': plan_code,
        'subscription_status': status,
        'subscription_amount_decimal': subscription_amount,
        'subscription_amount': float(subscription_amount),
        'subscription_interval': 'monthly',
        'subscription_autopay_enabled': 1 if form.get('subscription_autopay_enabled') in {'1', 'on', 'true', 'yes'} else 0,
        'subscription_next_billing_date': next_billing_date,
        'default_payment_method_label': default_payment_method_label,
        'default_payment_method_status': normalize_payment_method_status(form.get('default_payment_method_status', 'missing')),
        'backup_payment_method_label': backup_payment_method_label,
        'billing_notes': billing_notes,
    }, errors


def validate_payment_method_form(form, *, existing=None) -> tuple[dict, list[str]]:
    errors: list[str] = []
    label = form.get('label', '').strip()
    details_note = form.get('details_note', '').strip()
    method_type = normalize_payment_method_type(form.get('method_type', 'other'))
    status = normalize_saved_method_status(form.get('status', 'active'))
    holder_name = form.get('holder_name', '').strip()
    brand_name = form.get('brand_name', '').strip()
    card_number = clean_digits(form.get('card_number', '').strip())
    account_last4 = clean_last4(form.get('account_last4', '').strip())
    expiry_display = (form.get('expiry_display', '') or '').strip()
    routing_number = clean_digits(form.get('routing_number', '').strip())
    account_number = clean_digits(form.get('account_number', '').strip())
    confirm_account_number = clean_digits(form.get('confirm_account_number', '').strip())
    account_type = normalize_bank_account_type(form.get('account_type', 'checking'))
    existing_card_number = decrypt_secret((existing['card_number_enc'] or '')) if existing and 'card_number_enc' in existing.keys() else ''
    if not label:
        errors.append('Enter a payment method label.')
    elif len(label) > 120:
        errors.append('Payment method label must be 120 characters or fewer.')
    if len(holder_name) > 120:
        errors.append('Account holder name must be 120 characters or fewer.')
    if len(brand_name) > 80:
        errors.append('Card brand or bank name must be 80 characters or fewer.')
    if form.get('account_last4', '').strip() and len(account_last4) != 4:
        errors.append('Last 4 must contain exactly four digits.')
    if len(expiry_display) > 7:
        errors.append('Expiration must be in MM/YY format.')
    if expiry_display and not re.fullmatch(r'(0[1-9]|1[0-2])/\d{2}', expiry_display):
        errors.append('Expiration must use MM/YY format.')
    if method_type == 'card':
        if not brand_name:
            errors.append('Enter the card brand or issuer for card billing.')
        if not holder_name:
            errors.append('Enter the cardholder name for card billing.')
        if card_number:
            if len(card_number) < 13 or len(card_number) > 19:
                errors.append('Card number must be between 13 and 19 digits.')
        elif not existing_card_number and not account_last4 and not (existing['account_last4'] if existing else ''):
            errors.append('Enter a card number for card billing.')
    if method_type == 'ach':
        existing_routing = decrypt_secret((existing['routing_number_enc'] or '')) if existing else ''
        existing_account = decrypt_secret((existing['account_number_enc'] or '')) if existing else ''
        if not routing_number and not existing_routing:
            errors.append('Enter a routing number for ACH.')
        elif routing_number and len(routing_number) != 9:
            errors.append('Routing number must be 9 digits.')
        if not account_number and not existing_account:
            errors.append('Enter an account number for ACH.')
        elif account_number and len(account_number) < 4:
            errors.append('Account number must be at least 4 digits.')
        if account_number or confirm_account_number:
            if account_number != confirm_account_number:
                errors.append('Account number and confirmation must match.')
        if not holder_name:
            errors.append('Enter the account holder name for ACH.')
        if not brand_name:
            errors.append('Enter the bank name for ACH.')
    if len(details_note) > 300:
        errors.append('Payment method note must be 300 characters or fewer.')
    final_account_last4 = account_last4 or clean_last4(card_number) or clean_last4(account_number) or (existing['account_last4'] if existing else '')
    return {
        'method_type': method_type,
        'label': label,
        'status': status,
        'is_default': 1 if form.get('is_default') in {'1', 'on', 'true', 'yes'} else 0,
        'is_backup': 1 if form.get('is_backup') in {'1', 'on', 'true', 'yes'} else 0,
        'holder_name': holder_name[:120],
        'brand_name': brand_name[:80],
        'account_last4': final_account_last4,
        'expiry_display': expiry_display,
        'account_type': account_type,
        'card_number_enc': encrypt_secret(card_number) if card_number else (existing['card_number_enc'] if existing and 'card_number_enc' in existing.keys() else ''),
        'routing_number_enc': encrypt_secret(routing_number) if routing_number else (existing['routing_number_enc'] if existing else ''),
        'account_number_enc': encrypt_secret(account_number) if account_number else (existing['account_number_enc'] if existing else ''),
        'details_note': details_note,
    }, errors


def validate_worker_payout_setup(form, *, existing=None) -> tuple[dict, list[str]]:
    errors: list[str] = []
    payout_preference = normalize_worker_payout_preference(form.get('payout_preference', 'paper_check'))
    deposit_bank_name = form.get('deposit_bank_name', '').strip()[:80]
    deposit_account_holder_name = form.get('deposit_account_holder_name', '').strip()[:120]
    deposit_account_type = normalize_bank_account_type(form.get('deposit_account_type', 'checking'))
    deposit_account_last4 = clean_last4(form.get('deposit_account_last4', '').strip())
    deposit_routing_number = clean_digits(form.get('deposit_routing_number', '').strip())
    deposit_account_number = clean_digits(form.get('deposit_account_number', '').strip())
    confirm_deposit_account_number = clean_digits(form.get('confirm_deposit_account_number', '').strip())
    zelle_contact = form.get('zelle_contact', '').strip()[:120]
    existing = existing or {}
    existing_routing = decrypt_secret((existing['deposit_routing_number_enc'] or '')) if existing else ''
    existing_account = decrypt_secret((existing['deposit_account_number_enc'] or '')) if existing else ''

    if payout_preference == 'direct_deposit':
        if not deposit_bank_name:
            errors.append('Enter the bank name for direct deposit.')
        if not deposit_account_holder_name:
            errors.append('Enter the account holder name for direct deposit.')
        if not deposit_routing_number and not existing_routing:
            errors.append('Enter a routing number for direct deposit.')
        elif deposit_routing_number and len(deposit_routing_number) != 9:
            errors.append('Direct deposit routing number must be 9 digits.')
        if not deposit_account_number and not existing_account:
            errors.append('Enter an account number for direct deposit.')
        elif deposit_account_number and len(deposit_account_number) < 4:
            errors.append('Direct deposit account number must be at least 4 digits.')
        if deposit_account_number or confirm_deposit_account_number:
            if deposit_account_number != confirm_deposit_account_number:
                errors.append('Direct deposit account number and confirmation must match.')
    if payout_preference == 'zelle' and not zelle_contact:
        errors.append('Enter the Zelle email or phone number.')

    return {
        'payout_preference': payout_preference,
        'deposit_bank_name': deposit_bank_name,
        'deposit_account_holder_name': deposit_account_holder_name,
        'deposit_account_type': deposit_account_type,
        'deposit_account_last4': deposit_account_last4 or clean_last4(deposit_account_number) or (existing['deposit_account_last4'] if existing else ''),
        'deposit_routing_number_enc': encrypt_secret(deposit_routing_number) if deposit_routing_number else (existing['deposit_routing_number_enc'] if existing else ''),
        'deposit_account_number_enc': encrypt_secret(deposit_account_number) if deposit_account_number else (existing['deposit_account_number_enc'] if existing else ''),
        'zelle_contact': zelle_contact,
    }, errors


def payment_methods_for_client(client_id: int):
    with get_conn() as conn:
        return conn.execute(
            '''SELECT *
               FROM business_payment_methods
               WHERE client_id=?
               ORDER BY is_default DESC, is_backup DESC, updated_at DESC, id DESC''',
            (client_id,)
        ).fetchall()


def payment_method_display_label(method) -> str:
    label = (method['label'] or '').strip()
    if label:
        return label
    method_type = method['method_type'] or 'other'
    brand_or_bank = (method['brand_name'] or '').strip()
    last4 = (method['account_last4'] or '').strip()
    if method_type == 'card':
        parts = [brand_or_bank or 'Card']
        if last4:
            parts.append(f'ending in {last4}')
        return ' '.join(parts)
    if method_type in {'ach', 'zelle'}:
        parts = [brand_or_bank or 'Bank account']
        if last4:
            parts.append(f'ending in {last4}')
        return ' '.join(parts)
    return method_type.replace('_', ' ').title()


def payment_method_summary(methods) -> dict:
    rows = list(methods or [])
    default_method = next((row for row in rows if int(row['is_default'] or 0) == 1), rows[0] if rows else None)
    backup_method = next(
        (row for row in rows if int(row['is_backup'] or 0) == 1 and (not default_method or row['id'] != default_method['id'])),
        None,
    )
    active_count = sum(1 for row in rows if (row['status'] or 'active') == 'active')
    needs_update_count = sum(1 for row in rows if (row['status'] or 'active') == 'needs_update')
    return {
        'count': len(rows),
        'active_count': active_count,
        'needs_update_count': needs_update_count,
        'default_label': payment_method_display_label(default_method) if default_method else '',
        'default_status': (default_method['status'] or 'active') if default_method else 'missing',
        'default_type': (default_method['method_type'] or 'other') if default_method else '',
        'backup_label': payment_method_display_label(backup_method) if backup_method else '',
    }


def fee_collection_guidance(row) -> dict:
    collection_method = normalize_collection_method((row['collection_method'] or default_collection_method()))
    public_link = (row['public_payment_link'] or row['payment_link'] or '').strip()
    instructions = (row['payment_instructions'] or '').strip()
    if collection_method == 'send_payment_link' and public_link:
        return {
            'tone': 'action',
            'label': 'Pay Online',
            'detail': 'Open the administrator-provided payment page for this one-time fee.',
            'button_label': 'Open Payment Link',
            'url': public_link,
        }
    if collection_method == 'charge_saved_method':
        return {
            'tone': 'info',
            'label': 'Charge to Method on File',
            'detail': 'Your administrator marked this fee to be collected using the saved payment method on file. No self-service payment click is required on your side in this phase.',
            'button_label': '',
            'url': '',
        }
    if collection_method == 'manual_offline':
        return {
            'tone': 'info',
            'label': 'Manual Payment',
            'detail': instructions or 'Follow the manual payment instructions provided by your administrator for this fee.',
            'button_label': '',
            'url': '',
        }
    if collection_method == 'zelle_manual':
        return {
            'tone': 'info',
            'label': 'Bank / Zelle Instructions',
            'detail': instructions or 'Use the Zelle or bank-transfer instructions provided by your administrator for this fee.',
            'button_label': '',
            'url': '',
        }
    if collection_method == 'send_payment_request':
        return {
            'tone': 'pending',
            'label': 'Payment Request Pending',
            'detail': instructions or 'Your administrator will send or complete a payment request for this fee.',
            'button_label': '',
            'url': '',
        }
    if public_link:
        return {
            'tone': 'action',
            'label': 'Pay Online',
            'detail': 'Open the available payment page for this administrator fee.',
            'button_label': 'Open Payment Link',
            'url': public_link,
        }
    return {
        'tone': 'pending',
        'label': 'Payment Details Pending',
        'detail': 'This fee is posted, but your administrator has not added the payment action or instructions yet.',
        'button_label': '',
        'url': '',
    }


def open_fee_guidance(rows) -> dict:
    open_rows = [row for row in rows if (row['status'] or 'pending') in {'pending', 'processing'}]
    if not open_rows:
        return {
            'headline': 'No open administrator fees right now.',
            'detail': 'Your billing center is clear at the moment.',
        }
    return {
        'headline': 'Open administrator fees require review.',
        'detail': 'Review the fee actions below to complete payment.',
    }


def sync_client_payment_method_summary(conn: sqlite3.Connection, client_id: int):
    rows = conn.execute(
        '''SELECT *
           FROM business_payment_methods
           WHERE client_id=?
           ORDER BY is_default DESC, is_backup DESC, updated_at DESC, id DESC''',
        (client_id,)
    ).fetchall()
    default_row = next((row for row in rows if int(row['is_default'] or 0) == 1), rows[0] if rows else None)
    backup_row = next((row for row in rows if int(row['is_backup'] or 0) == 1 and (not default_row or row['id'] != default_row['id'])), None)
    conn.execute(
        '''UPDATE clients
           SET default_payment_method_label=?, default_payment_method_status=?, backup_payment_method_label=?
           WHERE id=?''',
        (
            (payment_method_display_label(default_row) if default_row else ''),
            ('on_file' if default_row and (default_row['status'] or 'active') == 'active' else 'missing' if not default_row else 'needs_update'),
            (payment_method_display_label(backup_row) if backup_row else ''),
            client_id,
        )
    )


def client_onboarding_is_complete(conn: sqlite3.Connection, client_row) -> bool:
    if not client_row:
        return False
    profile_ready = bool(
        (client_row['business_name'] or '').strip()
        and (client_row['contact_name'] or '').strip()
        and (client_row['email'] or '').strip()
    )
    subscription_ready = bool(
        normalize_service_level(client_row['service_level'] or default_service_level())
        and (client_row['subscription_plan_code'] or '').strip()
        and float(client_row['subscription_amount'] or 0) > 0
        and normalize_subscription_status(client_row['subscription_status'] or default_subscription_status()) == 'active'
    )
    payment_ready = bool(
        conn.execute(
            'SELECT 1 FROM business_payment_methods WHERE client_id=? AND COALESCE(status, "active")="active" LIMIT 1',
            (client_row['id'],)
        ).fetchone()
    )
    trial_ready = int(client_row['trial_offer_days'] or 0) > 0
    return profile_ready and subscription_ready and (trial_ready or payment_ready)


def user_requires_business_onboarding(user) -> bool:
    if not user or user['role'] != 'client' or not user['client_id']:
        return False
    with get_conn() as conn:
        row = conn.execute('SELECT onboarding_status FROM clients WHERE id=?', (user['client_id'],)).fetchone()
    return bool(row and (row['onboarding_status'] or 'completed') != 'completed')


def user_has_trial_offer(user) -> bool:
    if not user or user['role'] != 'client' or not user['client_id']:
        return False
    with get_conn() as conn:
        row = conn.execute('SELECT trial_offer_days FROM clients WHERE id=?', (user['client_id'],)).fetchone()
    return bool(row and int(row['trial_offer_days'] or 0) > 0)


def client_access_issue_from_row(client_row) -> dict | None:
    if not client_row:
        return {
            'state': 'missing',
            'headline': 'We could not find your business workspace.',
            'detail': 'Your LedgerFlow workspace record could not be found. Please contact your administrator to restore access.',
            'business_name': '',
        }
    record_status = (client_row['record_status'] or 'active').strip().lower()
    subscription_status = normalize_subscription_status(client_row['subscription_status'] or default_subscription_status())
    business_name = (client_row['business_name'] or 'your business').strip()
    if record_status == 'archived':
        return {
            'state': 'archived',
            'headline': f'We miss you at LedgerFlow, {business_name}.',
            'detail': 'This workspace is currently archived. Contact your administrator for a rejoin invitation to restore access.',
            'business_name': business_name,
        }
    if subscription_status == 'canceled':
        return {
            'state': 'subscription_canceled',
            'headline': f'We miss you at LedgerFlow, {business_name}.',
            'detail': 'Your subscription is currently canceled, so full workspace access is paused. Contact your administrator to reactivate and come back in.',
            'business_name': business_name,
        }
    return None


def client_access_issue_for_user(user) -> dict | None:
    if not user or user['role'] != 'client' or not user['client_id']:
        return None
    with get_conn() as conn:
        client_row = conn.execute(
            'SELECT business_name, subscription_status, record_status FROM clients WHERE id=?',
            (user['client_id'],)
        ).fetchone()
    return client_access_issue_from_row(client_row)


def worker_portal_access_allowed(worker_row) -> bool:
    if not worker_row:
        return False
    if (worker_row['status'] or 'active') != 'active':
        return False
    if int(worker_row['portal_access_enabled'] or 0) != 1:
        return False
    if (worker_row['portal_approval_status'] or 'approved') != 'approved':
        return False
    client_row = {
        'business_name': worker_row['business_name'] if 'business_name' in worker_row.keys() else '',
        'subscription_status': worker_row['client_subscription_status'] if 'client_subscription_status' in worker_row.keys() else default_subscription_status(),
        'record_status': worker_row['client_record_status'] if 'client_record_status' in worker_row.keys() else 'active',
    }
    return client_access_issue_from_row(client_row) is None


def validate_payment_item_form(form, *, require_client: bool = True) -> tuple[dict, list[str]]:
    errors: list[str] = []
    client_id = form.get('client_id', type=int) if require_client else None
    payment_type = normalize_payment_type(form.get('payment_type', default_payment_type()))
    collection_method = normalize_collection_method(form.get('collection_method', default_collection_method()))
    description = form.get('description', '').strip()
    amount_due = normalize_money_amount(form.get('amount_due', ''))
    due_date_raw = form.get('due_date', '').strip()
    payment_link = normalize_payment_link(form.get('payment_link', ''))
    public_payment_link = normalize_payment_link(form.get('public_payment_link', form.get('payment_link', '')))
    payment_instructions = form.get('payment_instructions', '').strip()
    note = form.get('note', '').strip()
    cancellation_note = form.get('cancellation_note', '').strip()
    status = form.get('status', 'pending').strip().lower()

    if require_client and not client_id:
        errors.append('Select a business.')
    if not description:
        errors.append('Enter a description or reference.')
    elif len(description) > 200:
        errors.append('Description must be 200 characters or fewer.')
    if amount_due is None:
        errors.append('Enter a valid amount due.')
    elif amount_due <= 0:
        errors.append('Amount due must be greater than zero.')
    due_date = ''
    if due_date_raw:
        parsed_due_date = parse_date(due_date_raw)
        if not parsed_due_date:
            errors.append('Enter a valid due date.')
        else:
            due_date = parsed_due_date.isoformat()
    if payment_link is None:
        errors.append('Payment link must be a full http:// or https:// URL.')
    elif len(payment_link) > 1000:
        errors.append('Payment link must be 1000 characters or fewer.')
    if public_payment_link is None:
        errors.append('Public payment link must be a full http:// or https:// URL.')
    elif len(public_payment_link) > 1000:
        errors.append('Public payment link must be 1000 characters or fewer.')
    if len(payment_instructions) > 500:
        errors.append('Payment instructions must be 500 characters or fewer.')
    if len(note) > 500:
        errors.append('Note must be 500 characters or fewer.')
    if len(cancellation_note) > 300:
        errors.append('Cancellation note must be 300 characters or fewer.')
    if status not in business_payment_statuses():
        errors.append('Select a valid payment status.')
    if collection_method not in {key for key, _ in collection_method_options()}:
        errors.append('Select a valid collection method.')

    return {
        'client_id': client_id,
        'payment_type': payment_type,
        'collection_method': collection_method,
        'description': description,
        'amount_due_decimal': amount_due,
        'amount_due': float(amount_due) if amount_due is not None else 0.0,
        'due_date': due_date,
        'payment_link': payment_link or '',
        'public_payment_link': public_payment_link or payment_link or '',
        'payment_instructions': payment_instructions,
        'note': note,
        'cancellation_note': cancellation_note,
        'status': status if status in business_payment_statuses() else 'pending',
    }, errors


def _fernet():
    secret = (app.config.get('SECRET_KEY') or '').encode('utf-8')
    digest = hashlib.sha256(secret).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    if not value:
        return ''
    return _fernet().encrypt(value.encode('utf-8')).decode('utf-8')


def decrypt_secret(value: str) -> str:
    if not value:
        return ''
    try:
        return _fernet().decrypt(value.encode('utf-8')).decode('utf-8')
    except Exception:
        return ''


def ensure_app_settings_table():
    with get_conn() as conn:
        conn.execute(
            '''CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT '',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )'''
        )
        conn.commit()


def ensure_email_settings_profile_table():
    with get_conn() as conn:
        conn.execute(
            '''CREATE TABLE IF NOT EXISTS email_settings_profile (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                smtp_email TEXT NOT NULL DEFAULT '',
                smtp_host TEXT NOT NULL DEFAULT 'smtp.gmail.com',
                smtp_port TEXT NOT NULL DEFAULT '587',
                smtp_username TEXT NOT NULL DEFAULT '',
                smtp_sender_name TEXT NOT NULL DEFAULT 'LedgerFlow',
                smtp_password_enc TEXT NOT NULL DEFAULT '',
                app_base_url TEXT NOT NULL DEFAULT '',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_by_user_id INTEGER,
                last_tested_at TEXT DEFAULT '',
                last_test_status TEXT DEFAULT '',
                last_test_recipient TEXT DEFAULT '',
                last_test_error TEXT DEFAULT '',
                FOREIGN KEY(updated_by_user_id) REFERENCES users(id)
            )'''
        )
        conn.commit()


def ensure_ai_assistant_profile_table():
    with get_conn() as conn:
        conn.execute(
            '''CREATE TABLE IF NOT EXISTS ai_assistant_profile (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                provider TEXT NOT NULL DEFAULT 'openai',
                enabled INTEGER NOT NULL DEFAULT 0,
                model TEXT NOT NULL DEFAULT 'gpt-5',
                api_key_enc TEXT NOT NULL DEFAULT '',
                assistant_label TEXT NOT NULL DEFAULT 'LedgerFlow Guide AI',
                system_prompt TEXT NOT NULL DEFAULT '',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_by_user_id INTEGER,
                last_tested_at TEXT DEFAULT '',
                last_test_status TEXT DEFAULT '',
                last_test_error TEXT DEFAULT '',
                FOREIGN KEY(updated_by_user_id) REFERENCES users(id)
            )'''
        )
        conn.commit()


def get_setting(key: str) -> str:
    ensure_app_settings_table()
    with get_conn() as conn:
        row = conn.execute('SELECT value FROM app_settings WHERE key=?', (key,)).fetchone()
    return (row['value'] if row else '') or ''


def set_setting(key: str, value: str):
    ensure_app_settings_table()
    with get_conn() as conn:
        conn.execute('INSERT INTO app_settings (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP', (key, value))
        conn.commit()


def load_email_runtime_config() -> dict:
    try:
        if EMAIL_CONFIG_PATH.exists():
            return json.loads(EMAIL_CONFIG_PATH.read_text(encoding='utf-8')) or {}
    except Exception:
        return {}
    return {}


def save_email_runtime_config(values: dict):
    current = load_email_runtime_config()
    current.update({k: (values.get(k) or '') for k in ['smtp_email', 'smtp_host', 'smtp_port', 'smtp_username', 'smtp_sender_name', 'smtp_password_enc', 'app_base_url']})
    EMAIL_CONFIG_PATH.write_text(json.dumps(current, indent=2), encoding='utf-8')


def legacy_email_settings_values() -> dict:
    runtime_cfg = load_email_runtime_config()
    return {
        'smtp_email': (get_setting('smtp_email') or runtime_cfg.get('smtp_email', '')).strip().lower(),
        'smtp_host': (get_setting('smtp_host') or runtime_cfg.get('smtp_host', '')).strip() or 'smtp.gmail.com',
        'smtp_port': (get_setting('smtp_port') or runtime_cfg.get('smtp_port', '')).strip() or '587',
        'smtp_username': (get_setting('smtp_username') or runtime_cfg.get('smtp_username', '')).strip(),
        'smtp_sender_name': (get_setting('smtp_sender_name') or runtime_cfg.get('smtp_sender_name', '')).strip() or APP_NAME,
        'smtp_password_enc': get_setting('smtp_password_enc') or runtime_cfg.get('smtp_password_enc', ''),
        'app_base_url': (get_setting('app_base_url') or runtime_cfg.get('app_base_url', '')).strip().rstrip('/'),
    }


def load_email_settings_profile() -> dict:
    ensure_email_settings_profile_table()
    with get_conn() as conn:
        row = conn.execute(
            '''SELECT esp.*, u.full_name updated_by_name
               FROM email_settings_profile esp
               LEFT JOIN users u ON u.id = esp.updated_by_user_id
               WHERE esp.id = 1'''
        ).fetchone()
        if row:
            return dict(row)

        legacy = legacy_email_settings_values()
        if any((legacy.get(key) or '').strip() for key in ['smtp_email', 'smtp_host', 'smtp_port', 'smtp_username', 'smtp_sender_name', 'smtp_password_enc', 'app_base_url']):
            conn.execute(
                '''INSERT INTO email_settings_profile (
                    id, smtp_email, smtp_host, smtp_port, smtp_username, smtp_sender_name, smtp_password_enc, app_base_url
                ) VALUES (1,?,?,?,?,?,?,?)''',
                (
                    legacy['smtp_email'],
                    legacy['smtp_host'],
                    legacy['smtp_port'],
                    legacy['smtp_username'] or legacy['smtp_email'],
                    legacy['smtp_sender_name'],
                    legacy['smtp_password_enc'],
                    legacy['app_base_url'],
                )
            )
            conn.commit()
            row = conn.execute(
                '''SELECT esp.*, u.full_name updated_by_name
                   FROM email_settings_profile esp
                   LEFT JOIN users u ON u.id = esp.updated_by_user_id
                   WHERE esp.id = 1'''
            ).fetchone()
            if row:
                return dict(row)

    return {
        'id': 1,
        'smtp_email': '',
        'smtp_host': 'smtp.gmail.com',
        'smtp_port': '587',
        'smtp_username': '',
        'smtp_sender_name': APP_NAME,
        'smtp_password_enc': '',
        'app_base_url': '',
        'updated_at': '',
        'updated_by_user_id': None,
        'updated_by_name': '',
        'last_tested_at': '',
        'last_test_status': '',
        'last_test_recipient': '',
        'last_test_error': '',
    }


def save_email_settings_profile(values: dict, updated_by_user_id=None):
    ensure_email_settings_profile_table()
    current = load_email_settings_profile()
    record = {
        'smtp_email': (values.get('smtp_email') or '').strip().lower(),
        'smtp_host': (values.get('smtp_host') or '').strip() or 'smtp.gmail.com',
        'smtp_port': (values.get('smtp_port') or '').strip() or '587',
        'smtp_username': (values.get('smtp_username') or '').strip() or (values.get('smtp_email') or '').strip().lower(),
        'smtp_sender_name': (values.get('smtp_sender_name') or '').strip() or APP_NAME,
        'smtp_password_enc': (values.get('smtp_password_enc') or current.get('smtp_password_enc') or '').strip(),
        'app_base_url': (values.get('app_base_url') or '').strip().rstrip('/'),
        'last_tested_at': current.get('last_tested_at', ''),
        'last_test_status': current.get('last_test_status', ''),
        'last_test_recipient': current.get('last_test_recipient', ''),
        'last_test_error': current.get('last_test_error', ''),
    }
    with get_conn() as conn:
        conn.execute(
            '''INSERT INTO email_settings_profile (
                id, smtp_email, smtp_host, smtp_port, smtp_username, smtp_sender_name, smtp_password_enc, app_base_url,
                updated_at, updated_by_user_id, last_tested_at, last_test_status, last_test_recipient, last_test_error
            ) VALUES (1,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                smtp_email=excluded.smtp_email,
                smtp_host=excluded.smtp_host,
                smtp_port=excluded.smtp_port,
                smtp_username=excluded.smtp_username,
                smtp_sender_name=excluded.smtp_sender_name,
                smtp_password_enc=excluded.smtp_password_enc,
                app_base_url=excluded.app_base_url,
                updated_at=CURRENT_TIMESTAMP,
                updated_by_user_id=excluded.updated_by_user_id,
                last_tested_at=excluded.last_tested_at,
                last_test_status=excluded.last_test_status,
                last_test_recipient=excluded.last_test_recipient,
                last_test_error=excluded.last_test_error''',
            (
                record['smtp_email'],
                record['smtp_host'],
                record['smtp_port'],
                record['smtp_username'],
                record['smtp_sender_name'],
                record['smtp_password_enc'],
                record['app_base_url'],
                updated_by_user_id,
                record['last_tested_at'],
                record['last_test_status'],
                record['last_test_recipient'],
                record['last_test_error'],
            )
        )
        conn.commit()


def record_email_settings_test_result(status: str, recipient_email: str = '', error_message: str = ''):
    ensure_email_settings_profile_table()
    profile = load_email_settings_profile()
    with get_conn() as conn:
        conn.execute(
            '''INSERT INTO email_settings_profile (
                id, smtp_email, smtp_host, smtp_port, smtp_username, smtp_sender_name, smtp_password_enc, app_base_url,
                updated_at, updated_by_user_id, last_tested_at, last_test_status, last_test_recipient, last_test_error
            ) VALUES (1,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,?,CURRENT_TIMESTAMP,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                last_tested_at=CURRENT_TIMESTAMP,
                last_test_status=excluded.last_test_status,
                last_test_recipient=excluded.last_test_recipient,
                last_test_error=excluded.last_test_error''',
            (
                profile.get('smtp_email', ''),
                profile.get('smtp_host', 'smtp.gmail.com'),
                profile.get('smtp_port', '587'),
                profile.get('smtp_username', ''),
                profile.get('smtp_sender_name', APP_NAME),
                profile.get('smtp_password_enc', ''),
                profile.get('app_base_url', ''),
                profile.get('updated_by_user_id'),
                (status or '').strip(),
                (recipient_email or '').strip().lower(),
                (error_message or '').strip()[:500],
            )
        )
        conn.commit()


def load_ai_assistant_profile() -> dict:
    ensure_ai_assistant_profile_table()
    with get_conn() as conn:
        row = conn.execute(
            '''SELECT ap.*, u.full_name updated_by_name
               FROM ai_assistant_profile ap
               LEFT JOIN users u ON u.id = ap.updated_by_user_id
               WHERE ap.id = 1'''
        ).fetchone()
        if row:
            return dict(row)
    return {
        'id': 1,
        'provider': 'openai',
        'enabled': 0,
        'model': 'gpt-5',
        'api_key_enc': '',
        'assistant_label': 'LedgerFlow Guide AI',
        'system_prompt': '',
        'updated_at': '',
        'updated_by_user_id': None,
        'updated_by_name': '',
        'last_tested_at': '',
        'last_test_status': '',
        'last_test_error': '',
    }


def save_ai_assistant_profile(values: dict, updated_by_user_id=None):
    ensure_ai_assistant_profile_table()
    current = load_ai_assistant_profile()
    record = {
        'provider': (values.get('provider') or current.get('provider') or 'openai').strip() or 'openai',
        'enabled': 1 if str(values.get('enabled', current.get('enabled', 0))).strip() in {'1', 'true', 'True'} or values.get('enabled') is True else 0,
        'model': (values.get('model') or current.get('model') or 'gpt-5').strip() or 'gpt-5',
        'api_key_enc': (values.get('api_key_enc') or current.get('api_key_enc') or '').strip(),
        'assistant_label': (values.get('assistant_label') or current.get('assistant_label') or 'LedgerFlow Guide AI').strip() or 'LedgerFlow Guide AI',
        'system_prompt': (values.get('system_prompt') or current.get('system_prompt') or '').strip(),
        'last_tested_at': current.get('last_tested_at', ''),
        'last_test_status': current.get('last_test_status', ''),
        'last_test_error': current.get('last_test_error', ''),
    }
    with get_conn() as conn:
        conn.execute(
            '''INSERT INTO ai_assistant_profile (
                id, provider, enabled, model, api_key_enc, assistant_label, system_prompt,
                updated_at, updated_by_user_id, last_tested_at, last_test_status, last_test_error
            ) VALUES (1,?,?,?,?,?,?,CURRENT_TIMESTAMP,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                provider=excluded.provider,
                enabled=excluded.enabled,
                model=excluded.model,
                api_key_enc=excluded.api_key_enc,
                assistant_label=excluded.assistant_label,
                system_prompt=excluded.system_prompt,
                updated_at=CURRENT_TIMESTAMP,
                updated_by_user_id=excluded.updated_by_user_id,
                last_tested_at=excluded.last_tested_at,
                last_test_status=excluded.last_test_status,
                last_test_error=excluded.last_test_error''',
            (
                record['provider'],
                record['enabled'],
                record['model'],
                record['api_key_enc'],
                record['assistant_label'],
                record['system_prompt'],
                updated_by_user_id,
                record['last_tested_at'],
                record['last_test_status'],
                record['last_test_error'],
            )
        )
        conn.commit()


def record_ai_assistant_test_result(status: str, error_message: str = ''):
    ensure_ai_assistant_profile_table()
    profile = load_ai_assistant_profile()
    with get_conn() as conn:
        conn.execute(
            '''INSERT INTO ai_assistant_profile (
                id, provider, enabled, model, api_key_enc, assistant_label, system_prompt,
                updated_at, updated_by_user_id, last_tested_at, last_test_status, last_test_error
            ) VALUES (1,?,?,?,?,?,?,CURRENT_TIMESTAMP,?,CURRENT_TIMESTAMP,?,?)
            ON CONFLICT(id) DO UPDATE SET
                last_tested_at=CURRENT_TIMESTAMP,
                last_test_status=excluded.last_test_status,
                last_test_error=excluded.last_test_error''',
            (
                profile.get('provider', 'openai'),
                int(profile.get('enabled') or 0),
                profile.get('model', 'gpt-5'),
                profile.get('api_key_enc', ''),
                profile.get('assistant_label', 'LedgerFlow Guide AI'),
                profile.get('system_prompt', ''),
                profile.get('updated_by_user_id'),
                (status or '').strip(),
                (error_message or '').strip()[:500],
            )
        )
        conn.commit()


def ai_assistant_config() -> dict:
    profile = load_ai_assistant_profile()
    api_key = decrypt_secret(profile.get('api_key_enc', ''))
    unreadable = bool(profile.get('api_key_enc') and not api_key)
    return {
        'enabled': bool(int(profile.get('enabled') or 0)),
        'provider': (profile.get('provider') or 'openai').strip() or 'openai',
        'model': (profile.get('model') or 'gpt-5').strip() or 'gpt-5',
        'assistant_label': (profile.get('assistant_label') or 'LedgerFlow Guide AI').strip() or 'LedgerFlow Guide AI',
        'system_prompt': (profile.get('system_prompt') or '').strip(),
        'api_key': api_key,
        'api_key_unreadable': unreadable,
        'configured': bool(int(profile.get('enabled') or 0)) and bool(api_key) and not unreadable,
        'profile': profile,
    }


def configured_base_url() -> str:
    profile = load_email_settings_profile()
    runtime_cfg = load_email_runtime_config()
    base = (profile.get('app_base_url') or get_setting('app_base_url') or runtime_cfg.get('app_base_url', '')).strip()
    cleaned = base.rstrip('/')
    for suffix in ('/main-portal', '/login', '/worker-login', '/business-comeback'):
        if cleaned.lower().endswith(suffix):
            cleaned = cleaned[:-len(suffix)]
            break
    return cleaned if cleaned else ''


def static_asset_version_value(filename: str) -> int:
    try:
        return int((BASE_DIR / 'static' / filename).stat().st_mtime)
    except OSError:
        return 0


def static_asset_url(filename: str) -> str:
    return url_for('static', filename=filename, v=static_asset_version_value(filename))


def static_asset_absolute_url(filename: str) -> str:
    path = static_asset_url(filename)
    base = configured_base_url().rstrip('/')
    return f"{base}{path}" if base else path


def require_configured_base_url() -> str:
    base = configured_base_url()
    if not base:
        raise RuntimeError('APP_BASE_URL is required before generating public invite links.')
    return base


def build_invite_link(token: str) -> str:
    base = require_configured_base_url()
    return f"{base}/business-invite/{token}"


def build_rejoin_link(token: str) -> str:
    base = require_configured_base_url()
    return f"{base}/business-rejoin/{token}"


def smtp_config():
    profile = load_email_settings_profile()
    runtime_cfg = load_email_runtime_config()
    sender_email = (profile.get('smtp_email') or get_setting('smtp_email') or runtime_cfg.get('smtp_email', '')).strip()
    sender_name = (profile.get('smtp_sender_name') or get_setting('smtp_sender_name') or runtime_cfg.get('smtp_sender_name', '')).strip() or APP_NAME
    smtp_host = (profile.get('smtp_host') or get_setting('smtp_host') or runtime_cfg.get('smtp_host', '')).strip() or 'smtp.gmail.com'
    smtp_port_raw = (profile.get('smtp_port') or get_setting('smtp_port') or runtime_cfg.get('smtp_port', '')).strip() or '587'
    smtp_username = (profile.get('smtp_username') or get_setting('smtp_username') or runtime_cfg.get('smtp_username', '')).strip() or sender_email
    pwd_enc = profile.get('smtp_password_enc') or get_setting('smtp_password_enc') or runtime_cfg.get('smtp_password_enc', '')
    password = decrypt_secret(pwd_enc)
    password_unreadable = bool(pwd_enc and not password)
    try:
        smtp_port = int(smtp_port_raw)
    except Exception:
        smtp_port = 587
    return {
        'sender_email': sender_email,
        'sender_name': sender_name,
        'smtp_host': smtp_host,
        'smtp_port': smtp_port,
        'smtp_username': smtp_username,
        'smtp_password': password,
        'password_unreadable': password_unreadable,
    }


def send_invite_email(to_email: str, to_name: str, business_name: str, invite_link: str):
    cfg = smtp_config()
    sender_email = cfg['sender_email']
    smtp_username = cfg['smtp_username']
    smtp_password = cfg['smtp_password']
    if cfg.get('password_unreadable'):
        raise RuntimeError('Saved SMTP password must be entered again once after the security-key update.')
    if not sender_email or not smtp_username or not smtp_password:
        raise RuntimeError('SMTP not configured')
    greeting = f"Hi {to_name}," if to_name else "Hi,"
    body = "\n".join([
        greeting,
        "",
        "Welcome to LedgerFlow.",
        f"You've been invited to create the business login for: {business_name}",
        "",
        "Use the secure link below to create your business login and begin workspace setup:",
        invite_link,
        "",
        "After your login is created, LedgerFlow will guide you through business setup, subscription selection, and payment-method setup before full workspace access is unlocked.",
        "",
        "If you were not expecting this invitation, you can ignore this email.",
        "",
        "LedgerFlow",
    ])
    html = render_marketing_email(
        eyebrow='Business Access Invite',
        title=f'Welcome to LedgerFlow',
        intro=f'Create secure access for {business_name} and continue into guided business setup.',
        greeting=greeting,
        body_lines=[
            'Use the button below to create your secure business login.',
            'After that, LedgerFlow will guide you through business details, subscription selection, and your payment method on file before full workspace access is unlocked.',
        ],
        cta_label='Create Business Login',
        cta_link=invite_link,
        detail_rows=[
            ('Business', business_name),
            ('Access email', to_email),
        ],
        feature_tags=['Billing Center', 'Income Records', 'Payroll Tax', 'Calendar Ready'],
        support_note='If you were not expecting this invitation, you can ignore this email.'
    )
    subject = f"Welcome to LedgerFlow - create access for {business_name}"
    send_rich_email(
        cfg,
        subject=subject,
        to_email=to_email,
        plain_text=body,
        html=html,
    )
    return {'subject': subject, 'body_text': body, 'body_html': html, 'email_type': 'business_invite'}


def send_trial_invite_email(to_email: str, to_name: str, business_name: str, invite_link: str, trial_days: int = 0, *, business_category: str = '', tracking_token: str = ''):
    cfg = smtp_config()
    sender_email = cfg['sender_email']
    smtp_username = cfg['smtp_username']
    smtp_password = cfg['smtp_password']
    if cfg.get('password_unreadable'):
        raise RuntimeError('Saved SMTP password must be entered again once after the security-key update.')
    if not sender_email or not smtp_username or not smtp_password:
        raise RuntimeError('SMTP not configured')
    if trial_days <= 0:
        trial_days = default_trial_offer_days()
    greeting = f"Hi {to_name}," if to_name else "Hi,"
    category_label = business_category_display(business_category)
    click_link = tracked_email_click_link(tracking_token, invite_link)
    tracking_pixel_url = email_tracking_pixel_url(tracking_token)
    trial_summary_html = (
        prospect_visual_card_html(business_category, business_name) +
        trial_offer_value_stack_html(business_category=business_category, trial_days=trial_days, stronger=False) +
        f"<div style='margin-top:20px;padding:18px 20px;border:1px solid #d7dce7;border-radius:18px;background:#ffffff'>"
        f"<div style='color:#141b2d;font-size:14px;font-weight:800'>Welcome tutorial preview</div>"
        f"<div style='margin-top:12px;display:flex;align-items:center;justify-content:center;min-height:160px;border-radius:16px;border:1px dashed #c9d2e0;background:linear-gradient(180deg,#f7f9fc,#eef2f6);color:#425067;font-size:14px;font-weight:700;text-align:center;padding:18px'>"
        f"Video-ready trial introduction<br>Open the trial page to watch the welcome walkthrough"
        f"</div>"
        f"<div style='margin-top:10px;color:#5b687d;font-size:13px;line-height:1.7'>Email clients do not reliably play embedded video, so this preview block takes the business directly into the full trial page where the welcome tutorial and setup guidance live together.</div>"
        f"</div>"
    )
    body = "\n".join([
        greeting,
        "",
        f"You've been invited to try LedgerFlow with a {trial_days}-day complimentary business trial for {business_name}.",
        f"Business category: {category_label}.",
        "",
        "Use the secure link below to review the subscription options, create your business login, and open the full trial experience:",
        invite_link,
        "",
        "No payment method is required to begin the complimentary trial.",
        "You'll choose the subscription that fits your business now, and you can add billing later before the complimentary trial window ends.",
        "",
        "If you were not expecting this invitation, you can ignore this email.",
        "",
        "LedgerFlow",
    ])
    email_html = render_marketing_email(
        eyebrow='Complimentary Trial Invite',
        title=f'Start your {trial_days}-day LedgerFlow trial',
        intro=f'Explore LedgerFlow for {business_name}, review the subscription options, and claim guided setup with a private client trial.',
        greeting=greeting,
        body_lines=[
            f'You have a {trial_days}-day complimentary window to explore the LedgerFlow business portal before monthly billing begins.',
            'Use the secure button below to review the offer, create your login, and open the full trial experience.',
            'No card is required to begin the complimentary trial.',
            'Your administrator remains directly involved, so the rollout feels white-glove from the first step.',
        ],
        cta_label=f'Open {trial_days}-Day Trial Experience',
        cta_link=click_link,
        detail_rows=[
            ('Business', business_name),
            ('Category', category_label),
            ('Trial Offer', f'{trial_days} complimentary days'),
            ('Invite Email', to_email),
        ],
        feature_tags=['7-Day Trial', 'Subscription Options', 'Guided Setup', 'Video Walkthrough Space'],
        support_note='If you were not expecting this invitation, you can ignore this email.',
        extra_sections_html=trial_summary_html,
        tracking_pixel_url=tracking_pixel_url,
    )
    subject = f"Start your {trial_days}-day LedgerFlow trial for {business_name}"
    send_rich_email(
        cfg,
        subject=subject,
        to_email=to_email,
        plain_text=body,
        html=email_html,
    )
    return {'subject': subject, 'body_text': body, 'body_html': email_html, 'email_type': 'prospect_trial_invite'}


def send_trial_followup_email(
    to_email: str,
    to_name: str,
    business_name: str,
    invite_link: str,
    *,
    trial_days: int = 0,
    business_category: str = '',
    tracking_token: str = '',
):
    cfg = smtp_config()
    sender_email = cfg['sender_email']
    smtp_username = cfg['smtp_username']
    smtp_password = cfg['smtp_password']
    if cfg.get('password_unreadable'):
        raise RuntimeError('Saved SMTP password must be entered again once after the security-key update.')
    if not sender_email or not smtp_username or not smtp_password:
        raise RuntimeError('SMTP not configured')
    if trial_days <= 0:
        trial_days = default_trial_offer_days()
    category_label = business_category_display(business_category)
    greeting = f"Hi {to_name}," if to_name else "Hi,"
    click_link = tracked_email_click_link(tracking_token, invite_link)
    tracking_pixel_url = email_tracking_pixel_url(tracking_token)
    stronger_sections_html = (
        prospect_visual_card_html(business_category, business_name) +
        trial_offer_value_stack_html(business_category=business_category, trial_days=trial_days, stronger=True) +
        f"<div style='margin-top:18px;padding:18px 20px;border:1px solid #dbe3ef;border-radius:18px;background:#ffffff'>"
        f"<div style='color:#141b2d;font-size:14px;font-weight:800;margin-bottom:12px'>Still deciding?</div>"
        f"<div style='color:#4a576d;font-size:14px;line-height:1.7'>Open the private trial page and you will see the pricing clearly, the guided setup path, and the exact LedgerFlow workspace your business would be stepping into. Nothing is charged today.</div>"
        f"</div>"
    )
    body = "\n".join([
        greeting,
        "",
        f"Your private {trial_days}-day LedgerFlow trial for {business_name} is still waiting.",
        f"This version is tailored for a {category_label} business and is designed to show the value faster in case the first invite was buried in another inbox tab.",
        "",
        "Use the secure link below to open the trial, review what your business is missing, and claim the complimentary access:",
        invite_link,
        "",
        "No payment method is required to begin the complimentary trial.",
        "You can explore the workspace first and add billing later only if LedgerFlow feels right for your business.",
        "",
        "If you were not expecting this invitation, you can ignore this email.",
        "",
        "LedgerFlow",
    ])
    email_html = render_marketing_email(
        eyebrow='Trial Follow-Up',
        title=f'Your {trial_days}-day LedgerFlow trial is still waiting',
        intro=f'Here is the faster view of what {business_name} can unlock inside LedgerFlow before the complimentary offer expires.',
        greeting=greeting,
        body_lines=[
            f'Your private {trial_days}-day trial is still open for {business_name}.',
            f'This follow-up is tailored for a {category_label} business and is designed to show the value faster.',
            'No card is required today. Open the trial, review the subscription options, and decide later if LedgerFlow is the right fit.',
            'If the first email was buried in Promotions or Spam, this is your shorter path back in.',
        ],
        cta_label='Open My Trial Now',
        cta_link=click_link,
        detail_rows=[
            ('Business', business_name),
            ('Category', category_label),
            ('Trial Offer', f'{trial_days} complimentary days'),
            ('Invite Email', to_email),
        ],
        feature_tags=['Higher-Value Follow-Up', 'No Card Required', 'Guided Setup', 'See What You Are Missing'],
        support_note='If you have any questions before opening the trial, reply to this email and your administrator can help.',
        extra_sections_html=stronger_sections_html,
        tracking_pixel_url=tracking_pixel_url,
    )
    subject = f"Still interested? Your LedgerFlow trial for {business_name} is waiting"
    send_rich_email(
        cfg,
        subject=subject,
        to_email=to_email,
        plain_text=body,
        html=email_html,
    )
    return {'subject': subject, 'body_text': body, 'body_html': email_html, 'email_type': 'prospect_trial_followup'}


def preferred_admin_notification_user_id(conn: sqlite3.Connection, client_id: int | None = None, fallback_user_id: int | None = None) -> int | None:
    if fallback_user_id:
        row = conn.execute(
            'SELECT id FROM users WHERE id=? AND role="admin"',
            (fallback_user_id,),
        ).fetchone()
        if row:
            return row['id']
    if client_id:
        row = conn.execute(
            '''SELECT created_by_user_id
               FROM business_invites
               WHERE client_id=? AND created_by_user_id IS NOT NULL
               ORDER BY created_at DESC, id DESC
               LIMIT 1''',
            (client_id,),
        ).fetchone()
        if row and row['created_by_user_id']:
            return row['created_by_user_id']
        row = conn.execute(
            'SELECT created_by_user_id, updated_by_user_id FROM clients WHERE id=?',
            (client_id,),
        ).fetchone()
        if row:
            for key in ('created_by_user_id', 'updated_by_user_id'):
                if row[key]:
                    admin_row = conn.execute(
                        'SELECT id FROM users WHERE id=? AND role="admin"',
                        (row[key],),
                    ).fetchone()
                    if admin_row:
                        return admin_row['id']
    row = conn.execute(
        'SELECT id FROM users WHERE role="admin" ORDER BY id LIMIT 1'
    ).fetchone()
    return row['id'] if row else None


def admin_notification_recipients(conn: sqlite3.Connection, preferred_admin_user_id: int | None = None):
    if preferred_admin_user_id:
        row = conn.execute(
            'SELECT id, email, full_name FROM users WHERE id=? AND role="admin" AND COALESCE(email,"")<>""',
            (preferred_admin_user_id,),
        ).fetchone()
        if row:
            return [row]
    return conn.execute(
        'SELECT id, email, full_name FROM users WHERE role="admin" AND COALESCE(email,"")<>"" ORDER BY id'
    ).fetchall()


def send_business_trial_claimed_email(
    to_email: str,
    to_name: str,
    business_name: str,
    *,
    trial_days: int,
    trial_end_date: str = '',
):
    cfg = smtp_config()
    sender_email = cfg['sender_email']
    smtp_username = cfg['smtp_username']
    smtp_password = cfg['smtp_password']
    if cfg.get('password_unreadable'):
        raise RuntimeError('Saved SMTP password must be entered again once after the security-key update.')
    if not sender_email or not smtp_username or not smtp_password:
        raise RuntimeError('SMTP not configured')
    login_link = public_app_url('/main-portal')
    greeting = f"Hi {to_name}," if to_name else "Hi,"
    trial_timing = f"Your complimentary access is active through {trial_end_date[:10]}." if trial_end_date else f"Your {trial_days}-day complimentary access is now active."
    body = "\n".join([
        greeting,
        "",
        f"We're excited you decided to start LedgerFlow for {business_name}.",
        trial_timing,
        "",
        "You can sign in now, open the Welcome Center, and continue the quick setup when you're ready.",
        "No payment method is required to begin the complimentary trial.",
        "",
        "Open LedgerFlow here:",
        login_link,
        "",
        "If you have any questions, reach out before the trial ends and we will help you personally.",
        "",
        "LedgerFlow",
    ])
    email_html = render_marketing_email(
        eyebrow='Trial Activated',
        title=f'Your LedgerFlow trial is ready for {business_name}',
        intro='We are excited to support your business while you explore the workspace and decide how you want to grow with LedgerFlow.',
        greeting=greeting,
        body_lines=[
            trial_timing,
            'Sign in now to open the Welcome Center, review the guided tutorial, and finish the quick setup when you are ready.',
            'No payment method is required to begin the complimentary trial.',
            'If you have any questions, reach out and we will help you move through it personally.',
        ],
        cta_label='Open Your Trial Workspace',
        cta_link=login_link,
        detail_rows=[
            ('Business', business_name),
            ('Trial Offer', f'{trial_days} complimentary days'),
            ('Login Email', to_email),
        ],
        feature_tags=['Welcome Center', 'Guided Setup', 'Upgrade Later', 'Direct Support'],
        support_note='If you were not expecting this message, you can ignore it.'
    )
    subject = f'Your LedgerFlow trial is ready for {business_name}'
    send_rich_email(
        cfg,
        subject=subject,
        to_email=to_email,
        plain_text=body,
        html=email_html,
    )
    return {'subject': subject, 'body_text': body, 'body_html': email_html, 'email_type': 'business_trial_claimed'}


def send_admin_trial_claimed_email(
    to_email: str,
    to_name: str,
    business_name: str,
    *,
    claimed_by_name: str,
    claimed_by_email: str,
    trial_days: int,
    claimed_at: str = '',
):
    cfg = smtp_config()
    sender_email = cfg['sender_email']
    smtp_username = cfg['smtp_username']
    smtp_password = cfg['smtp_password']
    if cfg.get('password_unreadable'):
        raise RuntimeError('Saved SMTP password must be entered again once after the security-key update.')
    if not sender_email or not smtp_username or not smtp_password:
        raise RuntimeError('SMTP not configured')
    portal_link = public_app_url('/main-portal')
    greeting = f"Hi {to_name}," if to_name else "Hi,"
    plain_lines = [
        greeting,
        "",
        f"The {trial_days}-day LedgerFlow trial for {business_name} has just been claimed.",
        f"Claimed by: {claimed_by_name or 'Business contact'}",
        f"Login email: {claimed_by_email}",
    ]
    if claimed_at:
        plain_lines.append(f"Claimed at: {claimed_at}")
    plain_lines.extend([
        "",
        "Open the administrator portal to review the invite pipeline, follow onboarding progress, and support the business directly.",
        portal_link,
        "",
        "LedgerFlow",
    ])
    email_html = render_marketing_email(
        eyebrow='Trial Claimed',
        title=f'{business_name} just claimed the complimentary trial',
        intro='The business owner created secure access and entered the trial workspace flow.',
        greeting=greeting,
        body_lines=[
            f'{claimed_by_name or "The business contact"} created the login for the trial workspace.',
            'Open the administrator portal to review the invite pipeline, confirm onboarding progress, and step in if support is needed.',
        ],
        cta_label='Open Administrator Portal',
        cta_link=portal_link,
        detail_rows=[
            ('Business', business_name),
            ('Claimed by', claimed_by_name or 'Business contact'),
            ('Login email', claimed_by_email),
            ('Offer', f'{trial_days}-day complimentary trial'),
            ('Claimed at', claimed_at),
        ],
        feature_tags=['Invite Tracking', 'Trial Claimed', 'Onboarding Follow-Up'],
        support_note='This message is part of the LedgerFlow administrator notification stream.'
    )
    subject = f'Trial claimed: {business_name}'
    send_rich_email(
        cfg,
        subject=subject,
        to_email=to_email,
        plain_text='\n'.join(plain_lines),
        html=email_html,
    )
    return {'subject': subject, 'body_text': '\n'.join(plain_lines), 'body_html': email_html, 'email_type': 'trial_claimed_notification'}


def send_admin_subscription_activation_email(
    to_email: str,
    to_name: str,
    business_name: str,
    *,
    activated_by_name: str,
    activated_by_email: str,
    tier_label: str,
    monthly_amount: float,
):
    cfg = smtp_config()
    sender_email = cfg['sender_email']
    smtp_username = cfg['smtp_username']
    smtp_password = cfg['smtp_password']
    if cfg.get('password_unreadable'):
        raise RuntimeError('Saved SMTP password must be entered again once after the security-key update.')
    if not sender_email or not smtp_username or not smtp_password:
        raise RuntimeError('SMTP not configured')
    portal_link = public_app_url('/main-portal')
    greeting = f"Hi {to_name}," if to_name else "Hi,"
    body = "\n".join([
        greeting,
        "",
        f"{business_name} completed setup and activated the {tier_label} subscription.",
        f"Activated by: {activated_by_name or 'Business contact'}",
        f"Login email: {activated_by_email}",
        f"Monthly amount: ${monthly_amount:.2f}",
        "",
        "Open the administrator portal to review the account, billing status, and next support steps.",
        portal_link,
        "",
        "LedgerFlow",
    ])
    email_html = render_marketing_email(
        eyebrow='Subscription Activated',
        title=f'{business_name} completed setup',
        intro='A business just moved from trial/setup into an active subscription state.',
        greeting=greeting,
        body_lines=[
            f'{activated_by_name or "The business contact"} finished the setup flow and activated the selected subscription.',
            'Open the administrator portal to confirm billing details, workspace readiness, and any next follow-up.',
        ],
        cta_label='Open Administrator Portal',
        cta_link=portal_link,
        detail_rows=[
            ('Business', business_name),
            ('Activated by', activated_by_name or 'Business contact'),
            ('Login email', activated_by_email),
            ('Subscription', tier_label),
            ('Monthly amount', f'${monthly_amount:.2f}'),
        ],
        feature_tags=['Activation Alert', 'Billing Ready', 'Client Growth'],
        support_note='This message is part of the LedgerFlow administrator notification stream.'
    )
    subject = f'Subscription activated: {business_name}'
    send_rich_email(
        cfg,
        subject=subject,
        to_email=to_email,
        plain_text=body,
        html=email_html,
    )
    return {'subject': subject, 'body_text': body, 'body_html': email_html, 'email_type': 'subscription_activation_notification'}


def send_rejoin_email(to_email: str, to_name: str, business_name: str, rejoin_link: str):
    cfg = smtp_config()
    sender_email = cfg['sender_email']
    smtp_username = cfg['smtp_username']
    smtp_password = cfg['smtp_password']
    if cfg.get('password_unreadable'):
        raise RuntimeError('Saved SMTP password must be entered again once after the security-key update.')
    if not sender_email or not smtp_username or not smtp_password:
        raise RuntimeError('SMTP not configured')
    greeting = f"Hi {to_name}," if to_name else "Hi,"
    body = "\n".join([
        greeting,
        "",
        f"You're invited to reopen LedgerFlow access for: {business_name}",
        "",
        "Use the secure link below to restore your workspace access.",
        rejoin_link,
        "",
        "If your previous business login still exists, LedgerFlow will guide you back to sign in.",
        "If no business login exists yet, LedgerFlow will guide you through creating one before access is restored.",
        "",
        "If you were not expecting this rejoin invitation, you can ignore this email.",
        "",
        "LedgerFlow",
    ])
    html = render_marketing_email(
        eyebrow='Business Rejoin Invite',
        title='Return to LedgerFlow',
        intro=f'Restore access for {business_name} and continue where your workspace left off.',
        greeting=greeting,
        body_lines=[
            'Use the button below to restore your business workspace access.',
            'If your business login already exists, LedgerFlow will send you to sign in after the workspace is reactivated.',
            'If a login still needs to be created, LedgerFlow will guide you through that securely first.',
        ],
        cta_label='Restore Workspace Access',
        cta_link=rejoin_link,
        detail_rows=[
            ('Business', business_name),
            ('Contact email', to_email),
        ],
        feature_tags=['Workspace Return', 'Billing Center', 'Income Records', 'Calendar Ready'],
        support_note='If you were not expecting this rejoin invitation, you can ignore this email.'
    )
    subject = f"LedgerFlow - restore access for {business_name}"
    send_rich_email(
        cfg,
        subject=subject,
        to_email=to_email,
        plain_text=body,
        html=html,
    )
    return {'subject': subject, 'body_text': body, 'body_html': html, 'email_type': 'business_rejoin'}


def send_customer_invoice_email(
    *,
    to_email: str,
    to_name: str,
    business_name: str,
    invoice_number,
    invoice_title: str,
    invoice_link: str,
    due_date: str,
    total_amount: float,
    payment_link: str = '',
):
    cfg = smtp_config()
    sender_email = cfg['sender_email']
    smtp_username = cfg['smtp_username']
    smtp_password = cfg['smtp_password']
    if cfg.get('password_unreadable'):
        raise RuntimeError('Saved SMTP password must be entered again once after the security-key update.')
    if not sender_email or not smtp_username or not smtp_password:
        raise RuntimeError('SMTP not configured')
    greeting = f"Hi {to_name}," if to_name else 'Hi,'
    title = invoice_title or 'Customer Invoice'
    due_line = f'Due date: {due_date}' if due_date else 'Due date: review the invoice page for the current payment timeline.'
    payment_note = 'A pay-online button is included on the invoice page.' if payment_link else 'Open the invoice page to view, print, and manage payment.'
    body = "\n".join([
        greeting,
        "",
        f"{business_name} sent you invoice #{invoice_number}: {title}",
        due_line,
        f"Invoice total: ${total_amount:.2f}",
        "",
        "Open your invoice here:",
        invoice_link,
        "",
        payment_note,
        "",
        "LedgerFlow",
    ])
    email_html = render_marketing_email(
        eyebrow='Customer Invoice',
        title=f'Invoice #{invoice_number} from {business_name}',
        intro='Review the invoice, print it if needed, and use the hosted page for the fastest next step.',
        greeting=greeting,
        body_lines=[
            f'{title} is ready for review.',
            due_line,
            f'Invoice total: ${total_amount:.2f}.',
            'Use the secure button below to open the hosted invoice page.',
            'If an online payment option was provided, it will appear directly on the invoice page.',
        ],
        cta_label='Open Invoice',
        cta_link=invoice_link,
        detail_rows=[
            ('Business', business_name),
            ('Invoice', f'#{invoice_number}'),
            ('Invoice title', title),
            ('Due date', due_date or 'View invoice page'),
            ('Invoice total', f'${total_amount:.2f}'),
        ],
        feature_tags=['Hosted Invoice', 'Print Ready', 'Pay Online Option', 'Paperless Billing'],
        support_note='If you were not expecting this invoice, contact the sender directly before making any payment.'
    )
    subject = f'Invoice #{invoice_number} from {business_name}'
    send_rich_email(
        cfg,
        subject=subject,
        to_email=to_email,
        plain_text=body,
        html=email_html,
    )
    return {'subject': subject, 'body_text': body, 'body_html': email_html, 'email_type': 'customer_invoice'}


def send_customer_invoice_reminder_email(
    *,
    to_email: str,
    to_name: str,
    business_name: str,
    invoice_number,
    invoice_title: str,
    invoice_link: str,
    due_date: str,
    balance_due: float,
    payment_link: str = '',
):
    cfg = smtp_config()
    sender_email = cfg['sender_email']
    smtp_username = cfg['smtp_username']
    smtp_password = cfg['smtp_password']
    if cfg.get('password_unreadable'):
        raise RuntimeError('Saved SMTP password must be entered again once after the security-key update.')
    if not sender_email or not smtp_username or not smtp_password:
        raise RuntimeError('SMTP not configured')
    greeting = f"Hi {to_name}," if to_name else 'Hi,'
    title = invoice_title or 'Customer Invoice'
    due_line = f'Due date: {due_date}' if due_date else 'Please review the invoice page for the current payment timeline.'
    payment_note = 'The invoice page includes the pay-online option that was provided.' if payment_link else 'Open the invoice page to review payment details.'
    body = "\n".join([
        greeting,
        "",
        f"This is a reminder about invoice #{invoice_number} from {business_name}: {title}",
        due_line,
        f"Balance due: ${balance_due:.2f}",
        "",
        "Open your invoice here:",
        invoice_link,
        "",
        payment_note,
        "",
        "LedgerFlow",
    ])
    email_html = render_marketing_email(
        eyebrow='Invoice Reminder',
        title=f'Reminder: invoice #{invoice_number}',
        intro='A business sent you a follow-up reminder so the invoice stays easy to find and complete.',
        greeting=greeting,
        body_lines=[
            f'{title} is still open.',
            due_line,
            f'Current balance due: ${balance_due:.2f}.',
            'Use the secure button below to reopen the hosted invoice page.',
            'If an online payment option was provided, it will appear directly on the invoice page.',
        ],
        cta_label='Review Invoice',
        cta_link=invoice_link,
        detail_rows=[
            ('Business', business_name),
            ('Invoice', f'#{invoice_number}'),
            ('Invoice title', title),
            ('Due date', due_date or 'Open invoice page'),
            ('Balance due', f'${balance_due:.2f}'),
        ],
        feature_tags=['Automatic Reminder', 'Hosted Invoice', 'Balance Due'],
        support_note='If you already handled this invoice, you can ignore this reminder.'
    )
    subject = f'Reminder: invoice #{invoice_number} from {business_name}'
    send_rich_email(
        cfg,
        subject=subject,
        to_email=to_email,
        plain_text=body,
        html=email_html,
    )
    return {'subject': subject, 'body_text': body, 'body_html': email_html, 'email_type': 'customer_invoice_reminder'}


def send_customer_receipt_email(
    *,
    to_email: str,
    to_name: str,
    business_name: str,
    invoice_number,
    invoice_title: str,
    invoice_link: str,
    paid_amount: float,
    paid_at: str,
):
    cfg = smtp_config()
    sender_email = cfg['sender_email']
    smtp_username = cfg['smtp_username']
    smtp_password = cfg['smtp_password']
    if cfg.get('password_unreadable'):
        raise RuntimeError('Saved SMTP password must be entered again once after the security-key update.')
    if not sender_email or not smtp_username or not smtp_password:
        raise RuntimeError('SMTP not configured')
    greeting = f"Hi {to_name}," if to_name else 'Hi,'
    title = invoice_title or 'Customer Invoice'
    paid_line = f'Paid on: {paid_at[:10]}' if paid_at else 'Paid status recorded in the hosted invoice page.'
    body = "\n".join([
        greeting,
        "",
        f"{business_name} recorded payment for invoice #{invoice_number}: {title}",
        paid_line,
        f"Amount received: ${paid_amount:.2f}",
        "",
        "Open the hosted invoice here:",
        invoice_link,
        "",
        "Thank you.",
        "",
        "LedgerFlow",
    ])
    email_html = render_marketing_email(
        eyebrow='Payment Receipt',
        title=f'Receipt for invoice #{invoice_number}',
        intro='This receipt confirms that payment was recorded on the hosted invoice.',
        greeting=greeting,
        body_lines=[
            f'{title} has been marked paid.',
            paid_line,
            f'Amount received: ${paid_amount:.2f}.',
            'Use the secure button below to reopen the hosted invoice or print it for your records.',
        ],
        cta_label='Open Receipt',
        cta_link=invoice_link,
        detail_rows=[
            ('Business', business_name),
            ('Invoice', f'#{invoice_number}'),
            ('Invoice title', title),
            ('Paid on', paid_at[:10] if paid_at else 'Recorded'),
            ('Amount received', f'${paid_amount:.2f}'),
        ],
        feature_tags=['Payment Receipt', 'Hosted Invoice', 'Print Ready'],
        support_note='If this receipt does not match your records, contact the sender directly.'
    )
    subject = f'Receipt for invoice #{invoice_number} from {business_name}'
    send_rich_email(
        cfg,
        subject=subject,
        to_email=to_email,
        plain_text=body,
        html=email_html,
    )
    return {'subject': subject, 'body_text': body, 'body_html': email_html, 'email_type': 'customer_receipt'}


def send_customer_estimate_email(
    *,
    to_email: str,
    to_name: str,
    business_name: str,
    estimate_number,
    estimate_title: str,
    estimate_link: str,
    valid_until: str,
    total_amount: float,
):
    cfg = smtp_config()
    sender_email = cfg['sender_email']
    smtp_username = cfg['smtp_username']
    smtp_password = cfg['smtp_password']
    if cfg.get('password_unreadable'):
        raise RuntimeError('Saved SMTP password must be entered again once after the security-key update.')
    if not sender_email or not smtp_username or not smtp_password:
        raise RuntimeError('SMTP not configured')
    greeting = f"Hi {to_name}," if to_name else 'Hi,'
    title = estimate_title or 'Project Estimate'
    valid_line = f'Valid through: {valid_until}' if valid_until else 'Review the estimate page for the current approval timeline.'
    body = "\n".join([
        greeting,
        "",
        f"{business_name} sent you estimate #{estimate_number}: {title}",
        valid_line,
        f"Estimated total: ${total_amount:.2f}",
        "",
        "Open your estimate here:",
        estimate_link,
        "",
        "You can review the scope and approve or decline it directly from the hosted page.",
        "",
        "LedgerFlow",
    ])
    email_html = render_marketing_email(
        eyebrow='Customer Estimate',
        title=f'Estimate #{estimate_number} from {business_name}',
        intro='Review the estimate, confirm the scope, and approve or decline it from the hosted page.',
        greeting=greeting,
        body_lines=[
            f'{title} is ready for review.',
            valid_line,
            f'Estimated total: ${total_amount:.2f}.',
            'Use the secure button below to open the hosted estimate page.',
            'You can approve or decline it directly from that page.',
        ],
        cta_label='Open Estimate',
        cta_link=estimate_link,
        detail_rows=[
            ('Business', business_name),
            ('Estimate', f'#{estimate_number}'),
            ('Estimate title', title),
            ('Valid through', valid_until or 'Open estimate page'),
            ('Estimated total', f'${total_amount:.2f}'),
        ],
        feature_tags=['Hosted Estimate', 'Approve Online', 'Decline Online', 'Paperless'],
        support_note='If you were not expecting this estimate, contact the sender directly before responding.'
    )
    subject = f'Estimate #{estimate_number} from {business_name}'
    send_rich_email(
        cfg,
        subject=subject,
        to_email=to_email,
        plain_text=body,
        html=email_html,
    )
    return {'subject': subject, 'body_text': body, 'body_html': email_html, 'email_type': 'customer_estimate'}


def smtp_email_ready() -> bool:
    cfg = smtp_config()
    return bool(cfg['sender_email'] and cfg['smtp_username'] and cfg['smtp_password'])


def render_marketing_email(*, eyebrow: str, title: str, intro: str, greeting: str, body_lines: list[str], cta_label: str = '', cta_link: str = '', detail_rows: list[tuple[str, str]] | None = None, feature_tags: list[str] | None = None, support_note: str = '', extra_sections_html: str = '', tracking_pixel_url: str = '') -> str:
    detail_rows = detail_rows or []
    feature_tags = feature_tags or []
    eyebrow_text = html.escape(eyebrow or '')
    title_text = html.escape(title or '')
    intro_text = html.escape(intro or '')
    greeting_text = html.escape(greeting or '')
    details_html = ''.join(
        f"<tr><td style='padding:8px 0;color:#5f6f86;font-size:13px;font-weight:700;white-space:nowrap'>{html.escape(label)}</td><td style='padding:8px 0 8px 18px;color:#16314f;font-size:14px;font-weight:600'>{html.escape(value)}</td></tr>"
        for label, value in detail_rows if value
    )
    feature_html = ''.join(
        f"<span style='display:inline-block;margin:0 8px 8px 0;padding:8px 12px;border-radius:999px;background:#f2f7ff;border:1px solid #d9e5fb;color:#224b7d;font-size:12px;font-weight:800;letter-spacing:.02em'>{html.escape(tag)}</span>"
        for tag in feature_tags
    )
    body_html = ''.join(
        f"<p style='margin:0 0 14px;color:#38506f;font-size:15px;line-height:1.7'>{html.escape(line)}</p>"
        for line in body_lines if line
    )
    cta_html = ''
    if cta_label and cta_link:
        cta_label_text = html.escape(cta_label)
        cta_link_text = html.escape(cta_link)
        cta_html = (
            "<table role='presentation' cellspacing='0' cellpadding='0' border='0' style='margin:24px 0 18px'>"
            "<tr>"
            f"<td style='border-radius:12px;background:#1f5db8;text-align:center'>"
            f"<a href='{cta_link_text}' style='display:inline-block;padding:14px 24px;color:#ffffff;text-decoration:none;font-size:15px;font-weight:800'>{cta_label_text}</a>"
            "</td>"
            "</tr>"
            "</table>"
            f"<div style='color:#6e7f96;font-size:12px;line-height:1.7'>If the button does not open, copy and paste this link into your browser:<br><span style='color:#1f5db8;word-break:break-all'>{cta_link_text}</span></div>"
        )
    support_html = f"<p style='margin:22px 0 0;color:#6e7f96;font-size:13px;line-height:1.7'>{html.escape(support_note)}</p>" if support_note else ''
    logo_url = html.escape(static_asset_absolute_url(BRAND_LOGO_FILENAME))
    logo_block = (
        f"<div style='display:inline-block;padding:14px 18px;border-radius:22px;background:linear-gradient(180deg,#ffffff,#f3f5f7);border:1px solid #d7e1ee;box-shadow:0 12px 30px rgba(21,26,44,.08)'>"
        f"<img src='{logo_url}' alt='{html.escape(APP_NAME)}' style='display:block;width:280px;max-width:100%;height:auto'>"
        f"</div>"
    )
    details_block = (
        f"<div style='margin:22px 0 0;padding:18px 20px;border:1px solid #dbe6f5;border-radius:16px;background:#f8fbff'>"
        f"<table role='presentation' style='width:100%;border-collapse:collapse'>{details_html}</table>"
        f"</div>"
        if details_html else ''
    )
    features_block = (
        f"<div style='margin:18px 0 0'>{feature_html}</div>"
        if feature_html else ''
    )
    tracking_pixel_html = (
        f"<img src='{html.escape(tracking_pixel_url)}' alt='' width='1' height='1' style='display:block;width:1px;height:1px;border:0;opacity:0'>"
        if tracking_pixel_url else ''
    )
    return f"""\
<!doctype html>
<html>
  <body style="margin:0;background:#eef3f9;padding:24px 12px;font-family:Arial,'Segoe UI',sans-serif;color:#16314f">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border-collapse:collapse;background:#eef3f9">
      <tr>
        <td align="center" style="padding:0">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:680px;border-collapse:collapse">
            <tr>
              <td style="padding:0 0 18px 0;text-align:center">
                {logo_block}
              </td>
            </tr>
            <tr>
              <td style="background:#173965;border-radius:24px 24px 0 0;padding:28px 32px 26px 32px">
                <div style="display:inline-block;padding:7px 12px;background:#2b4f86;border-radius:999px;color:#e8f0ff;font-size:11px;font-weight:800;letter-spacing:.12em;text-transform:uppercase">{eyebrow_text}</div>
                <div style="margin-top:18px;color:#ffffff;font-size:36px;line-height:1.08;font-weight:800">{title_text}</div>
                <div style="margin-top:12px;color:#d7e5fb;font-size:16px;line-height:1.7">{intro_text}</div>
              </td>
            </tr>
            <tr>
              <td style="background:#ffffff;border:1px solid #dbe5f1;border-top:none;border-radius:0 0 24px 24px;padding:30px 32px 32px 32px">
                {tracking_pixel_html}
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border-collapse:collapse">
                  <tr>
                    <td style="padding:0 0 18px 0;color:#16314f;font-size:15px;font-weight:700">{greeting_text}</td>
                  </tr>
                </table>
                {body_html}
                {cta_html}
                {details_block}
                {features_block}
                {extra_sections_html}
                {support_html}
                <div style="margin-top:26px;padding-top:18px;border-top:1px solid #e5edf7;color:#6b7d94;font-size:12px;line-height:1.7">
                  <strong style="display:block;color:#193452;font-size:13px;letter-spacing:.08em">{html.escape(APP_NAME.upper())}</strong>
                  {html.escape(BRAND_TAGLINE)}
                </div>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""


def send_rich_email(cfg: dict, *, subject: str, to_email: str, plain_text: str, html: str = ''):
    sender_email = cfg['sender_email']
    smtp_username = cfg['smtp_username']
    smtp_password = cfg['smtp_password']
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = f"{cfg['sender_name']} <{sender_email}>"
    msg['To'] = to_email
    msg.set_content(plain_text)
    if html:
        msg.add_alternative(html, subtype='html')
    with smtplib.SMTP(cfg['smtp_host'], cfg['smtp_port']) as s:
        s.ehlo()
        s.starttls()
        s.ehlo()
        s.login(smtp_username, smtp_password)
        s.send_message(msg)


def send_password_reset_email(to_email: str, reset_link: str, account_label: str = 'account'):
    cfg = smtp_config()
    sender_email = cfg['sender_email']
    smtp_username = cfg['smtp_username']
    smtp_password = cfg['smtp_password']
    if cfg.get('password_unreadable'):
        raise RuntimeError('Saved SMTP password must be entered again once after the security-key update.')
    if not sender_email or not smtp_username or not smtp_password:
        raise RuntimeError('SMTP not configured')
    body = "\n".join([
        f"We received a password reset request for your {APP_NAME} {account_label}.",
        "",
        "Use the link below to set a new password:",
        reset_link,
        "",
        "This link expires in 60 minutes. If you did not request this, you can ignore this email.",
    ])
    email_html = render_marketing_email(
        eyebrow='Password Reset',
        title=f'{APP_NAME} password reset',
        intro='Use the secure link below to choose a new password and get back into your workspace.',
        greeting='We received a password reset request.',
        body_lines=[
            f'This request was submitted for your {APP_NAME} {account_label}.',
            'Use the secure button below to set a new password.',
            'This link expires in 60 minutes. If you did not request this, you can safely ignore this email.',
        ],
        cta_label='Reset Password',
        cta_link=reset_link,
        feature_tags=['Secure Access', 'Password Reset'],
        support_note='If you continue having trouble signing in, contact your administrator for support.'
    )
    send_rich_email(cfg, subject=f'{APP_NAME} password reset request', to_email=to_email, plain_text=body, html=email_html)


def public_app_url(path: str) -> str:
    base = configured_base_url()
    if not base:
        root = (request.url_root or '').strip()
        base = root.rstrip('/') if root else ''
    clean_path = path if path.startswith('/') else f'/{path}'
    return f"{base}{clean_path}" if base else clean_path


def send_welcome_email(to_email: str, to_name: str = '', account_type: str = 'user', *, login_path: str = '/main-portal', business_name: str = '', reset_path: str = '/forgot-password'):
    cfg = smtp_config()
    sender_email = cfg['sender_email']
    smtp_username = cfg['smtp_username']
    smtp_password = cfg['smtp_password']
    if cfg.get('password_unreadable'):
        raise RuntimeError('Saved SMTP password must be entered again once after the security-key update.')
    if not sender_email or not smtp_username or not smtp_password:
        raise RuntimeError('SMTP not configured')

    account_title_map = {
        'business': 'Business Login',
        'worker': 'Worker Portal',
        'administrator': 'Administrator Account',
        'user': 'LedgerFlow Account',
    }
    account_title = account_title_map.get(account_type, 'LedgerFlow Account')
    login_link = public_app_url(login_path)
    reset_link = public_app_url(reset_path)
    greeting = f"Hi {to_name}," if to_name else 'Hello,'

    lines = [
        greeting,
        '',
        f'Welcome to LedgerFlow. Your {account_title.lower()} is ready.',
    ]
    if business_name:
        lines.append(f'Business workspace: {business_name}')
    lines.extend([
        '',
        'You can sign in here:',
        login_link,
        '',
        f'Login email: {to_email}',
        '',
        'For security, no password is included in this email.',
        'If you need to create or reset your password later, use the Forgot Password page here:',
        reset_link,
        '',
    ])

    if account_type == 'worker':
        lines.extend([
            'After signing in, you will only see your worker portal tools, such as schedule, time summary, pay stubs, messages, and requests.',
            '',
        ])
    elif account_type == 'business':
        lines.extend([
            'After signing in, you can access your business workspace, billing center, calendar, income records, worker tools, and assigned business services.',
            '',
        ])
    elif account_type == 'administrator':
        lines.extend([
            'After signing in, you can access the administrator workspace and system management tools.',
            '',
        ])

    lines.extend([
        'If you were not expecting this access, please contact your administrator.',
        '',
        'LedgerFlow',
    ])

    intro_map = {
        'business': 'Your business workspace is ready, and your core tools are waiting for you.',
        'worker': 'Your worker portal is ready with secure access to your schedule, time summary, pay stubs, and requests.',
        'administrator': 'Your administrator workspace is ready with system access, dashboards, and management tools.',
    }
    feature_map = {
        'business': ['Billing Center', 'Income Records', 'Calendar', 'Worker Tools'],
        'worker': ['Pay Stubs', 'Time Summary', 'Requests', 'Messenger'],
        'administrator': ['Dashboards', 'Billing Setup', 'Calendars', 'Compliance'],
    }
    html = render_marketing_email(
        eyebrow='Welcome',
        title=f'Your {account_title} is ready',
        intro=intro_map.get(account_type, 'Your LedgerFlow access is ready.'),
        greeting=greeting,
        body_lines=[
            f'Sign in with {to_email} using the secure login below.',
            'For security, no password is included in this email.',
            'If you need to create or reset your password later, use the password reset link shown below.',
        ] + ([f'Business workspace: {business_name}'] if business_name else []),
        cta_label='Open LedgerFlow',
        cta_link=login_link,
        detail_rows=[
            ('Account', account_title),
            ('Login email', to_email),
            ('Password reset', reset_link),
        ] + ([('Business', business_name)] if business_name else []),
        feature_tags=feature_map.get(account_type, ['LedgerFlow Access']),
        support_note='If you were not expecting this access, please contact your administrator.'
    )
    subject = f'Welcome to LedgerFlow - {account_title}'
    send_rich_email(
        cfg,
        subject=subject,
        to_email=to_email,
        plain_text='\n'.join(lines),
        html=html,
    )
    return {'subject': subject, 'body_text': '\n'.join(lines), 'body_html': html, 'email_type': f'{account_type}_welcome'}


def quarter_months(quarter: int):
    quarter = int(quarter)
    return {1: (1, 2, 3), 2: (4, 5, 6), 3: (7, 8, 9), 4: (10, 11, 12)}[quarter]


def quarter_date_range(year: int, quarter: int):
    months = quarter_months(quarter)
    start = date(year, months[0], 1)
    if quarter == 4:
        end = date(year, 12, 31)
    else:
        next_month = months[-1] + 1
        end = date(year, next_month, 1).fromordinal(date(year, next_month, 1).toordinal() - 1)
    return start, end


def pay_periods_per_year(frequency: str | None) -> int:
    return PAYROLL_PERIODS.get((frequency or 'weekly').lower(), 52)


def progressive_tax(amount: float, brackets: list[list[float]]) -> float:
    amount = max(float(amount or 0), 0.0)
    tax = 0.0
    for idx, (start, rate) in enumerate(brackets):
        end = brackets[idx + 1][0] if idx + 1 < len(brackets) else None
        if amount <= start:
            break
        taxable_slice = (min(amount, end) - start) if end is not None else (amount - start)
        if taxable_slice > 0:
            tax += taxable_slice * rate
    return money(tax)


def current_tax_rules(year: int):
    with get_conn() as conn:
        row = conn.execute('SELECT * FROM tax_rules WHERE tax_year=?', (int(year),)).fetchone()
    if row:
        return row
    return None


def deduction_field_for_status(status: str | None) -> str:
    status = (status or 'single').strip().lower()
    if status == 'married':
        return 'standard_deduction_married'
    if status == 'head':
        return 'standard_deduction_head'
    return 'standard_deduction_single'


def bracket_field_for_status(status: str | None) -> str:
    status = (status or 'single').strip().lower()
    if status == 'married':
        return 'brackets_married_json'
    if status == 'head':
        return 'brackets_head_json'
    return 'brackets_single_json'


def payer_profile_for_client(client_row):
    business_name = (client_row['business_name'] if client_row else '') or ''
    business_ein = (client_row['ein'] if client_row else '') or ''
    business_address = (client_row['address'] if client_row else '') or ''
    if business_ein.strip() == '12-3456789':
        business_ein = ''
    return {
        'payer_name': business_name,
        'payer_ein': business_ein,
        'payer_address': business_address,
    }


def inferred_withholding_periods(worker, payment, all_payments) -> int:
    default_periods = pay_periods_per_year(worker['payroll_frequency'])
    if not worker or worker['worker_type'] != 'W-2':
        return default_periods
    payments = list(all_payments or [])
    if not payments or not payment:
        return default_periods
    note = ((payment['note'] if 'note' in payment.keys() else '') or '').strip().lower()
    annual_note_tokens = ('annual', 'salary', 'year to date', 'year-to-date', 'ytd', 'full year')
    if any(token in note for token in annual_note_tokens):
        return 1
    if len(payments) == 1:
        gross_value = payment['amount'] if 'amount' in payment.keys() else payment['gross'] if 'gross' in payment.keys() else 0
        gross = float(gross_value or 0)
        frequency = (worker['payroll_frequency'] or 'weekly').lower()
        annual_thresholds = {
            'weekly': 5000.0,
            'biweekly': 10000.0,
            'semimonthly': 12000.0,
            'monthly': 25000.0,
        }
        if gross >= annual_thresholds.get(frequency, 10000.0):
            return 1
    return default_periods


def compute_withholding_for_payment(gross: float, worker, w4, tax_rules, annualization_periods: int | None = None) -> dict:
    gross = float(gross or 0)
    if gross <= 0 or not worker or worker['worker_type'] != 'W-2' or not tax_rules:
        return {
            'federal_withholding': 0.0,
            'employee_social_security': 0.0,
            'employee_medicare': 0.0,
            'employer_social_security': 0.0,
            'employer_medicare': 0.0,
            'employee_additional_medicare': 0.0,
            'net_check': money(gross),
        }
    periods = max(int(annualization_periods or pay_periods_per_year(worker['payroll_frequency']) or 1), 1)
    status = (w4['filing_status'] if w4 else 'single') or 'single'
    use_status = status
    if w4 and int(w4['multiple_jobs'] or 0):
        use_status = 'single' if status == 'married' else status
    standard_deduction = float(tax_rules[deduction_field_for_status(use_status)] or 0)
    brackets = json.loads(tax_rules[bracket_field_for_status(use_status)] or '[]')
    annual_wages = gross * periods
    annual_other_income = float(w4['other_income'] or 0) if w4 else 0.0
    annual_deductions = float(w4['deductions'] or 0) if w4 else 0.0
    extra_per_period = float(w4['extra_withholding'] or 0) if w4 else 0.0
    annual_credits = ((float(w4['qualifying_children'] or 0) * 2000) + (float(w4['other_dependents'] or 0) * 500)) if w4 else 0.0
    annual_taxable = max(annual_wages + annual_other_income - annual_deductions - standard_deduction, 0.0)
    annual_tax = progressive_tax(annual_taxable, brackets)
    annual_tax = max(annual_tax - annual_credits, 0.0)
    federal = money((annual_tax / periods) + extra_per_period)
    ss_rate_emp = float(tax_rules['social_security_rate_employee'] or 0)
    ss_rate_er = float(tax_rules['social_security_rate_employer'] or 0)
    med_rate_emp = float(tax_rules['medicare_rate_employee'] or 0)
    med_rate_er = float(tax_rules['medicare_rate_employer'] or 0)
    annual_ss_base = float(tax_rules['social_security_wage_base'] or 0)
    ss_taxable = min(gross, annual_ss_base) if annual_ss_base else gross
    emp_ss = money(ss_taxable * ss_rate_emp)
    er_ss = money(ss_taxable * ss_rate_er)
    emp_med = money(gross * med_rate_emp)
    er_med = money(gross * med_rate_er)
    net = money(gross - federal - emp_ss - emp_med)
    return {
        'federal_withholding': federal,
        'employee_social_security': emp_ss,
        'employee_medicare': emp_med,
        'employer_social_security': er_ss,
        'employer_medicare': er_med,
        'employee_additional_medicare': 0.0,
        'net_check': net,
    }


def  compute_worker_payment_rollup(worker, payments, tax_rules):
    annual_ss_base = float(tax_rules['social_security_wage_base'] or 0) if tax_rules else 0.0
    addl_threshold = float(tax_rules['additional_medicare_threshold'] or 200000) if tax_rules else 200000.0
    addl_rate = float(tax_rules['additional_medicare_rate'] or ADDITIONAL_MEDICARE_RATE) if tax_rules else ADDITIONAL_MEDICARE_RATE
    ytd_gross = 0.0
    details = []
    totals = {
        'gross': 0.0, 'federal_withholding': 0.0, 'social_security_wages': 0.0, 'social_security_tax_total': 0.0,
        'medicare_wages': 0.0, 'medicare_tax_total': 0.0, 'employee_social_security': 0.0, 'employer_social_security': 0.0,
        'employee_medicare': 0.0, 'employer_medicare': 0.0, 'additional_medicare_wages': 0.0, 'additional_medicare_tax': 0.0,
        'net_check': 0.0
    }
    w4 = None
    with get_conn() as conn:
        w4 = conn.execute('SELECT * FROM w4_answers WHERE worker_id=?', (worker['id'],)).fetchone()
    for p in payments:
        gross = float(p['amount'] or 0)
        pay_calc = compute_withholding_for_payment(gross, worker, w4, tax_rules, annualization_periods=inferred_withholding_periods(worker, p, payments))
        if worker['worker_type'] == 'W-2':
            remaining_ss = max(annual_ss_base - ytd_gross, 0.0)
            ss_taxable = min(gross, remaining_ss)
            addl_taxable = max((ytd_gross + gross) - addl_threshold, 0.0) - max(ytd_gross - addl_threshold, 0.0)
            addl_taxable = max(addl_taxable, 0.0)
            emp_ss = money(ss_taxable * float(tax_rules['social_security_rate_employee']))
            er_ss = money(ss_taxable * float(tax_rules['social_security_rate_employer']))
            emp_med = money(gross * float(tax_rules['medicare_rate_employee']))
            er_med = money(gross * float(tax_rules['medicare_rate_employer']))
            addl_tax = money(addl_taxable * addl_rate)
            federal = pay_calc['federal_withholding']
            net = money(gross - federal - emp_ss - emp_med - addl_tax)
        else:
            ss_taxable = addl_taxable = emp_ss = er_ss = emp_med = er_med = addl_tax = federal = 0.0
            net = money(gross)
        detail = {
            'id': p['id'],
            'payment_date': p['payment_date'],
            'note': p['note'],
            'gross': money(gross),
            'federal_withholding': money(federal),
            'social_security_wages': money(ss_taxable),
            'employee_social_security': money(emp_ss),
            'employer_social_security': money(er_ss),
            'medicare_wages': money(gross if worker['worker_type']=='W-2' else 0),
            'employee_medicare': money(emp_med),
            'employer_medicare': money(er_med),
            'additional_medicare_wages': money(addl_taxable),
            'additional_medicare_tax': money(addl_tax),
            'net_check': money(net),
            'worker_name': worker['name'],
            'worker_type': worker['worker_type'],
        }
        details.append(detail)
        for key in totals:
            if key in detail:
                totals[key] = money(totals[key] + detail[key])
        ytd_gross += gross
    return {'details': details, 'totals': totals}


def estimate_w2_federal(total: float, w4) -> float:
    tax_rules = current_tax_rules(date.today().year)
    worker = {'worker_type': 'W-2', 'payroll_frequency': 'monthly'}
    calc = compute_withholding_for_payment(total, worker, w4, tax_rules, annualization_periods=1) if tax_rules else {'federal_withholding': round(float(total or 0) * FEDERAL_WITHHOLDING_RATE, 2)}
    return money(calc['federal_withholding'])

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / 'templates'),
    static_folder=str(BASE_DIR / 'static'),
)
IS_PRODUCTION = any([
    (os.environ.get('APP_ENV') or '').strip().lower() == 'production',
    (os.environ.get('FLASK_ENV') or '').strip().lower() == 'production',
    bool((os.environ.get('RENDER') or '').strip()),
    bool((os.environ.get('RENDER_EXTERNAL_URL') or '').strip()),
])

local_secret_path = DATA_DIR / '.local_secret_key'
secret_key = (os.environ.get('SECRET_KEY') or os.environ.get('ClearLedger_SECRET') or '').strip()
if not secret_key:
    try:
        if local_secret_path.exists():
            secret_key = local_secret_path.read_text(encoding='utf-8').strip()
        if not secret_key and not IS_PRODUCTION:
            secret_key = secrets.token_urlsafe(32)
            local_secret_path.write_text(secret_key, encoding='utf-8')
    except Exception:
        if not IS_PRODUCTION:
            secret_key = secrets.token_urlsafe(32)
if IS_PRODUCTION and not secret_key:
    raise RuntimeError('SECRET_KEY must be set in production or available as .local_secret_key in DATA_DIR.')
app.config['SECRET_KEY'] = secret_key

app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = IS_PRODUCTION or os.environ.get('SESSION_COOKIE_SECURE', '0') == '1'


def ai_guide_visible() -> bool:
    raw = (os.environ.get('AI_GUIDE_VISIBLE') or '').strip().lower()
    if raw in {'1', 'true', 'yes', 'on'}:
        return True
    if raw in {'0', 'false', 'no', 'off'}:
        return False
    return not IS_PRODUCTION


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def log_account_activity(conn, *, client_id=None, account_type='login', account_email='', account_name='', created_by_user_id=None, status='created', detail=''):
    conn.execute(
        """INSERT INTO account_activity_log (client_id, account_type, account_email, account_name, created_by_user_id, status, detail)
           VALUES (?,?,?,?,?,?,?)""",
        (client_id, account_type, (account_email or '').strip().lower(), (account_name or '').strip(), created_by_user_id, status, (detail or '').strip())
    )


def log_email_delivery(*, client_id=None, email_type='', recipient_email='', recipient_name='', subject='', body_text='', body_html='', status='sent', error_message='', created_by_user_id=None, related_invite_id=None, related_user_id=None, tracking_token: str = '', opened_at: str = '', open_count: int = 0, clicked_at: str = '', click_count: int = 0, conn: sqlite3.Connection | None = None):
    owns_connection = conn is None
    db = conn or get_conn()
    db.execute(
        """INSERT INTO email_delivery_log
           (client_id, email_type, recipient_email, recipient_name, subject, body_text, body_html, status, error_message, created_by_user_id, related_invite_id, related_user_id, tracking_token, opened_at, open_count, clicked_at, click_count)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            client_id,
            (email_type or '').strip(),
            (recipient_email or '').strip().lower(),
            (recipient_name or '').strip(),
            (subject or '').strip(),
            body_text or '',
            body_html or '',
            (status or 'sent').strip(),
            (error_message or '').strip()[:500],
            created_by_user_id,
            related_invite_id,
            related_user_id,
            (tracking_token or '').strip(),
            (opened_at or '').strip(),
            int(open_count or 0),
            (clicked_at or '').strip(),
            int(click_count or 0),
        )
    )
    if owns_connection:
        db.commit()
        db.close()


def now_iso() -> str:
    return datetime.now().isoformat(timespec='seconds')


def parse_datetime_value(value: str) -> datetime | None:
    text = (value or '').strip()
    if not text:
        return None
    for candidate in (text, text.replace('Z', '+00:00')):
        try:
            parsed = datetime.fromisoformat(candidate)
            return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
        except ValueError:
            continue
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S'):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    return None


def generate_email_tracking_token() -> str:
    return secrets.token_urlsafe(24)


def client_profile_snapshot(source) -> dict:
    row = dict(source or {})
    for key in ('bank_account_number', 'bank_routing_number', 'credit_card_number'):
        if row.get(key):
            row[key] = '[protected]'
    return row


def worker_profile_snapshot(source) -> dict:
    row = dict(source or {})
    if row.get('ssn'):
        row['ssn'] = f'***-**-{clean_last4(row["ssn"])}' if clean_last4(row['ssn']) else '[protected]'
    for key in ('portal_password_hash', 'deposit_routing_number_enc', 'deposit_account_number_enc'):
        if row.get(key):
            row[key] = '[protected]'
    return row


def log_client_profile_history(conn: sqlite3.Connection, *, client_id: int, action: str, changed_by_user_id=None, snapshot=None, detail: str = ''):
    row = snapshot or conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
    if not row:
        return
    payload = json.dumps(client_profile_snapshot(row), sort_keys=True, default=str)
    conn.execute(
        '''INSERT INTO client_profile_history (client_id, action, snapshot_json, changed_by_user_id, detail, changed_at)
           VALUES (?,?,?,?,?,?)''',
        (client_id, action.strip()[:50], payload, changed_by_user_id, (detail or '').strip()[:300], now_iso())
    )


def log_worker_profile_history(conn: sqlite3.Connection, *, worker_id: int, client_id: int, action: str, changed_by_user_id=None, snapshot=None, detail: str = ''):
    row = snapshot or conn.execute('SELECT * FROM workers WHERE id=?', (worker_id,)).fetchone()
    if not row:
        return
    payload = json.dumps(worker_profile_snapshot(row), sort_keys=True, default=str)
    conn.execute(
        '''INSERT INTO worker_profile_history (worker_id, client_id, action, snapshot_json, changed_by_user_id, detail, changed_at)
           VALUES (?,?,?,?,?,?,?)''',
        (worker_id, client_id, action.strip()[:50], payload, changed_by_user_id, (detail or '').strip()[:300], now_iso())
    )


def email_preview_html(html_body: str) -> str:
    if not html_body:
        return ''

    def replace_anchor(match: re.Match) -> str:
        attrs = match.group(1) or ''
        inner = match.group(2) or ''
        attrs = re.sub(r'\shref\s*=\s*(".*?"|\'.*?\'|[^\s>]+)', '', attrs, flags=re.IGNORECASE | re.DOTALL)
        attrs = re.sub(r'\starget\s*=\s*(".*?"|\'.*?\'|[^\s>]+)', '', attrs, flags=re.IGNORECASE | re.DOTALL)
        attrs = re.sub(r'\srel\s*=\s*(".*?"|\'.*?\'|[^\s>]+)', '', attrs, flags=re.IGNORECASE | re.DOTALL)
        attrs = re.sub(r'\son[a-z]+\s*=\s*(".*?"|\'.*?\'|[^\s>]+)', '', attrs, flags=re.IGNORECASE | re.DOTALL)
        attrs = attrs.rstrip()
        return (
            f"<span{attrs} style=\"pointer-events:none;cursor:default;text-decoration:none;\">"
            f"{inner}</span>"
        )

    preview = re.sub(
        r'<a([^>]*)>(.*?)</a>',
        replace_anchor,
        html_body,
        flags=re.IGNORECASE | re.DOTALL,
    )
    preview_note = (
        "<div style=\"margin:0 0 16px 0;padding:12px 14px;border-radius:14px;"
        "background:#f5f9ff;border:1px solid #dbe8fb;color:#2c4f77;font-size:13px;"
        "line-height:1.6;font-weight:600\">Preview mode: email links are disabled here. "
        "Use this page to review the message only.</div>"
    )
    return preview_note + preview


def record_email_open_event(tracking_token: str) -> bool:
    token = (tracking_token or '').strip()
    if not token:
        return False
    with get_conn() as conn:
        row = conn.execute(
            'SELECT id, status, open_count FROM email_delivery_log WHERE tracking_token=? ORDER BY id DESC LIMIT 1',
            (token,),
        ).fetchone()
        if not row:
            return False
        opened_at = now_iso()
        next_count = int(row['open_count'] or 0) + 1
        next_status = row['status'] if row['status'] in {'clicked', 'failed'} else 'opened'
        conn.execute(
            'UPDATE email_delivery_log SET opened_at=CASE WHEN COALESCE(opened_at,"")="" THEN ? ELSE opened_at END, open_count=?, status=? WHERE id=?',
            (opened_at, next_count, next_status, row['id']),
        )
        conn.commit()
    return True


def record_email_click_event(tracking_token: str) -> bool:
    token = (tracking_token or '').strip()
    if not token:
        return False
    with get_conn() as conn:
        row = conn.execute(
            'SELECT id, click_count FROM email_delivery_log WHERE tracking_token=? ORDER BY id DESC LIMIT 1',
            (token,),
        ).fetchone()
        if not row:
            return False
        clicked_at = now_iso()
        next_count = int(row['click_count'] or 0) + 1
        conn.execute(
            'UPDATE email_delivery_log SET clicked_at=CASE WHEN COALESCE(clicked_at,"")="" THEN ? ELSE clicked_at END, click_count=?, status="clicked" WHERE id=?',
            (clicked_at, next_count, row['id']),
        )
        conn.commit()
    return True


def prospect_email_attention_state(row) -> dict:
    initial_opened = bool((row.get('last_invite_email_opened_at') or '').strip() or int(row.get('last_invite_email_open_count') or 0) > 0)
    initial_clicked = bool((row.get('last_invite_email_clicked_at') or '').strip() or int(row.get('last_invite_email_click_count') or 0) > 0)
    followup_sent_at = (row.get('followup_sent_at') or '').strip()
    followup_status = (row.get('followup_status') or '').strip().lower()
    invite_created_at = parse_datetime_value(row.get('invite_created_at') or row.get('created_at') or '')
    due_for_followup = bool(invite_created_at and datetime.utcnow() - invite_created_at >= timedelta(days=3))

    if initial_clicked:
        return {
            'label': 'Clicked',
            'detail': 'The prospect clicked into the trial experience from the email.',
            'tone': 'accepted',
        }
    if initial_opened:
        return {
            'label': 'Opened',
            'detail': 'The prospect opened the invite email, so a spam-box follow-up is not needed.',
            'tone': 'sent',
        }
    if followup_status == 'sent' and followup_sent_at:
        return {
            'label': 'Follow-Up Sent',
            'detail': 'No open signal was recorded after 3 days, so LedgerFlow sent a higher-value follow-up. This may mean the first email was ignored or buried in Promotions/Spam, but SMTP cannot confirm the exact folder.',
            'tone': 'processing',
        }
    if followup_status == 'failed':
        return {
            'label': 'Follow-Up Failed',
            'detail': row.get('followup_error') or 'The automatic follow-up attempted to send and failed.',
            'tone': 'failed',
        }
    if due_for_followup:
        return {
            'label': 'No Open Signal',
            'detail': 'No open was recorded after 3 days. That often means the first email was ignored or filtered into inbox tabs, Promotions, or Spam, but it cannot be confirmed from SMTP alone.',
            'tone': 'pending',
        }
    return {
        'label': 'Awaiting Open',
        'detail': 'The invite email was sent and LedgerFlow is waiting for the first open or click signal.',
        'tone': 'sent',
    }


def process_due_prospect_followups(triggered_by_user_id: int | None = None) -> dict:
    if not smtp_email_ready():
        return {'sent': 0, 'failed': 0, 'skipped': 0}
    results = {'sent': 0, 'failed': 0, 'skipped': 0}
    with get_conn() as conn:
        due_rows = conn.execute(
            """SELECT
                   bi.*,
                   c.business_name,
                   c.business_category,
                   c.contact_name,
                   c.email AS client_email,
                   COALESCE(c.trial_offer_days, bi.trial_days, 0) AS effective_trial_days,
                   (
                       SELECT edl.opened_at
                       FROM email_delivery_log edl
                       WHERE edl.related_invite_id = bi.id
                         AND edl.email_type = 'prospect_trial_invite'
                       ORDER BY edl.created_at DESC, edl.id DESC
                       LIMIT 1
                   ) AS invite_opened_at,
                   (
                       SELECT edl.open_count
                       FROM email_delivery_log edl
                       WHERE edl.related_invite_id = bi.id
                         AND edl.email_type = 'prospect_trial_invite'
                       ORDER BY edl.created_at DESC, edl.id DESC
                       LIMIT 1
                   ) AS invite_open_count,
                   (
                       SELECT edl.clicked_at
                       FROM email_delivery_log edl
                       WHERE edl.related_invite_id = bi.id
                         AND edl.email_type = 'prospect_trial_invite'
                       ORDER BY edl.created_at DESC, edl.id DESC
                       LIMIT 1
                   ) AS invite_clicked_at,
                   (
                       SELECT edl.click_count
                       FROM email_delivery_log edl
                       WHERE edl.related_invite_id = bi.id
                         AND edl.email_type = 'prospect_trial_invite'
                       ORDER BY edl.created_at DESC, edl.id DESC
                       LIMIT 1
                   ) AS invite_click_count
               FROM business_invites bi
               JOIN clients c ON c.id = bi.client_id
               WHERE bi.invite_kind = 'prospect_trial'
                 AND bi.status = 'sent'
                 AND COALESCE(c.record_status, 'active') = 'prospect'
                 AND COALESCE(bi.followup_status, 'pending') IN ('', 'pending')
                 AND COALESCE(bi.followup_sent_at, '') = ''
                 AND bi.accepted_user_id IS NULL
                 AND datetime(bi.created_at) <= datetime('now', '-3 days')
               ORDER BY bi.created_at ASC, bi.id ASC"""
        ).fetchall()
        for row in due_rows:
            if (row['invite_opened_at'] or '').strip() or int(row['invite_open_count'] or 0) > 0 or (row['invite_clicked_at'] or '').strip() or int(row['invite_click_count'] or 0) > 0:
                conn.execute(
                    'UPDATE business_invites SET followup_status="not_needed", followup_error="" WHERE id=?',
                    (row['id'],),
                )
                results['skipped'] += 1
                continue
            lock_value = now_iso()
            updated = conn.execute(
                'UPDATE business_invites SET followup_status="processing", followup_error="" WHERE id=? AND COALESCE(followup_status,"pending") IN ("", "pending") AND COALESCE(followup_sent_at,"")=""',
                (row['id'],),
            )
            conn.commit()
            if not updated.rowcount:
                continue
            tracking_token = generate_email_tracking_token()
            try:
                payload = send_trial_followup_email(
                    row['invited_email'],
                    row['invited_name'],
                    row['business_name'],
                    build_invite_link(row['token']),
                    trial_days=int(row['effective_trial_days'] or default_trial_offer_days()),
                    business_category=row['business_category'] or '',
                    tracking_token=tracking_token,
                )
                conn.execute(
                    'UPDATE business_invites SET followup_sent_at=?, followup_status="sent", followup_error="" WHERE id=?',
                    (lock_value, row['id']),
                )
                log_email_delivery(
                    client_id=row['client_id'],
                    email_type=payload['email_type'],
                    recipient_email=row['invited_email'],
                    recipient_name=row['invited_name'],
                    subject=payload['subject'],
                    body_text=payload['body_text'],
                    body_html=payload['body_html'],
                    status='sent',
                    created_by_user_id=triggered_by_user_id or row['created_by_user_id'],
                    related_invite_id=row['id'],
                    tracking_token=tracking_token,
                    conn=conn,
                )
                conn.commit()
                results['sent'] += 1
            except Exception as exc:
                conn.execute(
                    'UPDATE business_invites SET followup_status="failed", followup_error=? WHERE id=?',
                    (str(exc)[:500], row['id']),
                )
                log_email_delivery(
                    client_id=row['client_id'],
                    email_type='prospect_trial_followup',
                    recipient_email=row['invited_email'],
                    recipient_name=row['invited_name'],
                    subject=f"Still interested? Your LedgerFlow trial for {row['business_name']} is waiting",
                    status='failed',
                    error_message=str(exc)[:500],
                    created_by_user_id=triggered_by_user_id or row['created_by_user_id'],
                    related_invite_id=row['id'],
                    tracking_token=tracking_token,
                    conn=conn,
                )
                conn.commit()
                results['failed'] += 1
    return results


def recent_email_activity(ids=None, limit=30):
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT edl.*, c.business_name, u.full_name created_by_name
               FROM email_delivery_log edl
               LEFT JOIN clients c ON c.id = edl.client_id
               LEFT JOIN users u ON u.id = edl.created_by_user_id
               ORDER BY edl.created_at DESC, edl.id DESC
               LIMIT ?""",
            (limit,)
        ).fetchall()
    if ids is None:
        return rows
    allowed = set(ids)
    return [r for r in rows if (r['client_id'] in allowed) or (r['client_id'] is None)]


def per_business_login_counts(ids=None):
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT c.id, c.business_name,
                      COUNT(DISTINCT CASE WHEN u.role='client' THEN u.id END) AS business_login_count,
                      COUNT(DISTINCT CASE WHEN COALESCE(w.portal_access_enabled,0)=1 THEN w.id END) AS worker_portal_count
               FROM clients c
               LEFT JOIN users u ON u.client_id = c.id AND u.role='client'
               LEFT JOIN workers w ON w.client_id = c.id
               GROUP BY c.id, c.business_name
               ORDER BY c.business_name"""
        ).fetchall()
    allowed = set(ids) if ids is not None else None
    out = []
    for row in rows:
        if allowed is not None and row['id'] not in allowed:
            continue
        business_count = int(row['business_login_count'] or 0)
        worker_count = int(row['worker_portal_count'] or 0)
        out.append({
            'client_id': row['id'],
            'business_name': row['business_name'],
            'business_login_count': business_count,
            'worker_portal_count': worker_count,
            'total_login_count': business_count + worker_count,
        })
    return out


def recent_account_activity(ids=None, limit=20):
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT aal.*, c.business_name, u.full_name created_by_name
               FROM account_activity_log aal
               LEFT JOIN clients c ON c.id = aal.client_id
               LEFT JOIN users u ON u.id = aal.created_by_user_id
               ORDER BY aal.created_at DESC, aal.id DESC
               LIMIT ?""",
            (limit,)
        ).fetchall()
    if ids is None:
        return rows
    allowed = set(ids)
    return [r for r in rows if (r['client_id'] in allowed) or (r['client_id'] is None)]


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str):
    cols = [r['name'] for r in conn.execute(f'PRAGMA table_info({table})').fetchall()]
    if column not in cols:
        conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')


def init_db():
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin','client')),
                client_id INTEGER,
                preferred_language TEXT DEFAULT 'en',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_name TEXT NOT NULL,
                business_type TEXT DEFAULT '',
                business_category TEXT DEFAULT '',
                business_specialty TEXT DEFAULT '',
                preferred_language TEXT DEFAULT 'en',
                service_level TEXT DEFAULT 'self_service',
                access_service_level TEXT DEFAULT '',
                access_override_note TEXT DEFAULT '',
                subscription_plan_code TEXT DEFAULT '',
                subscription_status TEXT DEFAULT 'inactive',
                subscription_amount REAL NOT NULL DEFAULT 0,
                subscription_interval TEXT DEFAULT 'monthly',
                subscription_autopay_enabled INTEGER NOT NULL DEFAULT 0,
                subscription_next_billing_date TEXT DEFAULT '',
                subscription_started_at TEXT DEFAULT '',
                subscription_canceled_at TEXT DEFAULT '',
                subscription_paused_at TEXT DEFAULT '',
                onboarding_status TEXT DEFAULT 'completed',
                onboarding_started_at TEXT DEFAULT '',
                onboarding_completed_at TEXT DEFAULT '',
                onboarding_completed_by_user_id INTEGER,
                record_status TEXT DEFAULT 'active',
                archive_reason TEXT DEFAULT '',
                archived_at TEXT DEFAULT '',
                archived_by_user_id INTEGER,
                reactivated_at TEXT DEFAULT '',
                default_payment_method_label TEXT DEFAULT '',
                default_payment_method_status TEXT DEFAULT 'missing',
                backup_payment_method_label TEXT DEFAULT '',
                billing_notes TEXT DEFAULT '',
                contact_name TEXT,
                phone TEXT,
                email TEXT,
                address TEXT,
                ein TEXT,
                eftps_status TEXT DEFAULT 'Not Enrolled',
                eftps_login_reference TEXT DEFAULT '',
                filing_type TEXT DEFAULT 'Both',
                bank_name TEXT DEFAULT '',
                bank_account_nickname TEXT DEFAULT '',
                bank_account_last4 TEXT DEFAULT '',
                bank_account_holder_name TEXT DEFAULT '',
                bank_account_number TEXT DEFAULT '',
                bank_routing_number TEXT DEFAULT '',
                credit_card_nickname TEXT DEFAULT '',
                credit_card_last4 TEXT DEFAULT '',
                credit_card_holder_name TEXT DEFAULT '',
                credit_card_number TEXT DEFAULT '',
                payroll_contact_name TEXT DEFAULT '',
                payroll_contact_phone TEXT DEFAULT '',
                payroll_contact_email TEXT DEFAULT '',
                state_tax_id TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                job_number INTEGER,
                record_kind TEXT NOT NULL DEFAULT 'income_record',
                invoice_title TEXT DEFAULT '',
                client_name TEXT NOT NULL,
                recipient_email TEXT DEFAULT '',
                client_address TEXT,
                invoice_total_amount REAL NOT NULL DEFAULT 0,
                paid_amount REAL DEFAULT 0,
                invoice_date TEXT,
                due_date TEXT DEFAULT '',
                estimate_expiration_date TEXT DEFAULT '',
                invoice_status TEXT NOT NULL DEFAULT 'draft',
                public_invoice_token TEXT DEFAULT '',
                public_payment_link TEXT DEFAULT '',
                sent_at TEXT DEFAULT '',
                last_reminder_at TEXT DEFAULT '',
                reminder_count INTEGER NOT NULL DEFAULT 0,
                customer_viewed_at TEXT DEFAULT '',
                customer_paid_at TEXT DEFAULT '',
                approved_at TEXT DEFAULT '',
                declined_at TEXT DEFAULT '',
                converted_invoice_id INTEGER,
                payment_note TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(client_id) REFERENCES clients(id),
                FOREIGN KEY(converted_invoice_id) REFERENCES invoices(id)
            );
            CREATE TABLE IF NOT EXISTS customer_contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                customer_name TEXT NOT NULL,
                customer_email TEXT DEFAULT '',
                customer_phone TEXT DEFAULT '',
                customer_address TEXT DEFAULT '',
                customer_notes TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                created_by_user_id INTEGER,
                updated_by_user_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(client_id) REFERENCES clients(id)
            );
            CREATE TABLE IF NOT EXISTS gas_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                week_start TEXT,
                amount REAL DEFAULT 0,
                note TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(client_id) REFERENCES clients(id)
            );
            CREATE TABLE IF NOT EXISTS workers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                worker_type TEXT NOT NULL,
                ssn TEXT DEFAULT '',
                address TEXT DEFAULT '',
                phone TEXT DEFAULT '',
                email TEXT DEFAULT '',
                preferred_language TEXT DEFAULT 'en',
                hire_date TEXT DEFAULT '',
                pay_notes TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(client_id) REFERENCES clients(id)
            );
            CREATE TABLE IF NOT EXISTS client_profile_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                action TEXT NOT NULL DEFAULT 'updated',
                snapshot_json TEXT NOT NULL DEFAULT '{}',
                changed_by_user_id INTEGER,
                detail TEXT DEFAULT '',
                changed_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS worker_profile_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                worker_id INTEGER NOT NULL,
                client_id INTEGER NOT NULL,
                action TEXT NOT NULL DEFAULT 'updated',
                snapshot_json TEXT NOT NULL DEFAULT '{}',
                changed_by_user_id INTEGER,
                detail TEXT DEFAULT '',
                changed_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS worker_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                worker_id INTEGER NOT NULL,
                payment_date TEXT,
                amount REAL DEFAULT 0,
                payment_method TEXT DEFAULT 'direct_deposit',
                payment_status TEXT DEFAULT 'paid',
                reference_number TEXT DEFAULT '',
                note TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(worker_id) REFERENCES workers(id)
            );
            CREATE TABLE IF NOT EXISTS worker_time_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                worker_id INTEGER NOT NULL,
                entry_date TEXT NOT NULL,
                hours REAL NOT NULL DEFAULT 0,
                note TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(worker_id) REFERENCES workers(id)
            );
            CREATE TABLE IF NOT EXISTS worker_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                worker_id INTEGER NOT NULL,
                sender_kind TEXT NOT NULL DEFAULT 'worker',
                sender_user_id INTEGER,
                body TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                is_read_worker INTEGER NOT NULL DEFAULT 1,
                is_read_manager INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(worker_id) REFERENCES workers(id),
                FOREIGN KEY(sender_user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS worker_time_off_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                worker_id INTEGER NOT NULL,
                request_type TEXT NOT NULL DEFAULT 'Day Off',
                start_date TEXT NOT NULL,
                end_date TEXT DEFAULT '',
                note TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(worker_id) REFERENCES workers(id)
            );
            CREATE TABLE IF NOT EXISTS work_schedule_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                job_name TEXT NOT NULL,
                job_address TEXT DEFAULT '',
                scope_of_work TEXT DEFAULT '',
                schedule_date TEXT NOT NULL,
                start_time TEXT DEFAULT '',
                end_time TEXT DEFAULT '',
                estimated_duration TEXT DEFAULT '',
                assigned_worker_ids TEXT DEFAULT '',
                assigned_worker_names TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                created_by_user_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(client_id) REFERENCES clients(id),
                FOREIGN KEY(created_by_user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS materials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                material_date TEXT,
                description TEXT,
                amount REAL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(client_id) REFERENCES clients(id)
            );
            CREATE TABLE IF NOT EXISTS mileage_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                trip_date TEXT,
                from_address TEXT DEFAULT '',
                to_address TEXT DEFAULT '',
                purpose TEXT DEFAULT '',
                miles REAL DEFAULT 0,
                deduction REAL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(client_id) REFERENCES clients(id)
            );
            CREATE TABLE IF NOT EXISTS invoice_mileage_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                invoice_id INTEGER,
                trip_date TEXT,
                start_point TEXT DEFAULT '',
                destination TEXT DEFAULT '',
                trip_type TEXT DEFAULT 'two_way',
                round_trips INTEGER DEFAULT 1,
                one_way_miles REAL DEFAULT 0,
                total_miles REAL DEFAULT 0,
                rate REAL DEFAULT 0,
                total_amount REAL DEFAULT 0,
                note TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(client_id) REFERENCES clients(id),
                FOREIGN KEY(invoice_id) REFERENCES invoices(id)
            );
            CREATE TABLE IF NOT EXISTS invoice_line_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id INTEGER NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                description TEXT NOT NULL DEFAULT '',
                quantity REAL NOT NULL DEFAULT 1,
                unit_price REAL NOT NULL DEFAULT 0,
                line_total REAL NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(invoice_id) REFERENCES invoices(id)
            );
            CREATE TABLE IF NOT EXISTS other_expenses_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                expense_date TEXT NOT NULL,
                vendor_description TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'other',
                amount REAL NOT NULL DEFAULT 0,
                note TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(client_id) REFERENCES clients(id)
            );
            CREATE TABLE IF NOT EXISTS business_payment_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                payment_type TEXT NOT NULL DEFAULT 'other',
                is_admin_fee INTEGER NOT NULL DEFAULT 1,
                collection_method TEXT NOT NULL DEFAULT 'send_payment_request',
                description TEXT NOT NULL,
                amount_due REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                due_date TEXT DEFAULT '',
                payment_link TEXT DEFAULT '',
                public_payment_link TEXT DEFAULT '',
                payment_instructions TEXT DEFAULT '',
                note TEXT DEFAULT '',
                cancellation_note TEXT DEFAULT '',
                archived_at TEXT DEFAULT '',
                created_by_user_id INTEGER,
                paid_at TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(client_id) REFERENCES clients(id),
                FOREIGN KEY(created_by_user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS business_payment_methods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                method_type TEXT NOT NULL DEFAULT 'other',
                label TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                is_default INTEGER NOT NULL DEFAULT 0,
                is_backup INTEGER NOT NULL DEFAULT 0,
                holder_name TEXT DEFAULT '',
                brand_name TEXT DEFAULT '',
                account_last4 TEXT DEFAULT '',
                expiry_display TEXT DEFAULT '',
                account_type TEXT DEFAULT '',
                card_number_enc TEXT DEFAULT '',
                routing_number_enc TEXT DEFAULT '',
                account_number_enc TEXT DEFAULT '',
                details_note TEXT DEFAULT '',
                created_by_user_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(client_id) REFERENCES clients(id),
                FOREIGN KEY(created_by_user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS worker_policy_notices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                created_by_user_id INTEGER,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(client_id) REFERENCES clients(id),
                FOREIGN KEY(created_by_user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS w4_answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                worker_id INTEGER UNIQUE NOT NULL,
                filing_status TEXT DEFAULT '',
                multiple_jobs INTEGER DEFAULT 0,
                qualifying_children REAL DEFAULT 0,
                other_dependents REAL DEFAULT 0,
                other_income REAL DEFAULT 0,
                deductions REAL DEFAULT 0,
                extra_withholding REAL DEFAULT 0,
                signature_name TEXT DEFAULT '',
                signed_date TEXT DEFAULT '',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(worker_id) REFERENCES workers(id)
            );
            CREATE TABLE IF NOT EXISTS tax_rules (
                tax_year INTEGER PRIMARY KEY,
                social_security_rate_employee REAL NOT NULL,
                social_security_rate_employer REAL NOT NULL,
                social_security_wage_base REAL NOT NULL,
                medicare_rate_employee REAL NOT NULL,
                medicare_rate_employer REAL NOT NULL,
                additional_medicare_rate REAL NOT NULL,
                additional_medicare_threshold REAL NOT NULL,
                standard_deduction_single REAL NOT NULL,
                standard_deduction_married REAL NOT NULL,
                standard_deduction_head REAL NOT NULL,
                brackets_single_json TEXT NOT NULL,
                brackets_married_json TEXT NOT NULL,
                brackets_head_json TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS payroll_tax_deposits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                deposit_date TEXT NOT NULL,
                tax_year INTEGER NOT NULL,
                tax_quarter INTEGER NOT NULL,
                tax_month INTEGER NOT NULL,
                amount REAL NOT NULL DEFAULT 0,
                payment_method TEXT DEFAULT 'EFTPS',
                confirmation_number TEXT DEFAULT '',
                note TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(client_id) REFERENCES clients(id)
            );
            
            CREATE TABLE IF NOT EXISTS payroll_review_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                submitted_by INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','needs_correction')),
                note TEXT DEFAULT '',
                submitted_at TEXT DEFAULT CURRENT_TIMESTAMP,
                reviewed_by INTEGER,
                reviewed_at TEXT DEFAULT '',
                review_note TEXT DEFAULT '',
                FOREIGN KEY(client_id) REFERENCES clients(id),
                FOREIGN KEY(submitted_by) REFERENCES users(id),
                FOREIGN KEY(reviewed_by) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS internal_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                sender_user_id INTEGER NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(client_id) REFERENCES clients(id),
                FOREIGN KEY(sender_user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS admin_calendar_reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_user_id INTEGER NOT NULL,
                reminder_type TEXT NOT NULL,
                reminder_date TEXT NOT NULL,
                note TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(admin_user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS business_calendar_reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                created_by_user_id INTEGER NOT NULL,
                reminder_type TEXT NOT NULL,
                reminder_date TEXT NOT NULL,
                note TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(client_id) REFERENCES clients(id),
                FOREIGN KEY(created_by_user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS admin_todo_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                due_date TEXT DEFAULT '',
                priority TEXT DEFAULT 'medium',
                is_completed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT DEFAULT '',
                FOREIGN KEY(admin_user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS business_help_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                submitted_by_user_id INTEGER NOT NULL,
                request_type TEXT DEFAULT '',
                message TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(client_id) REFERENCES clients(id),
                FOREIGN KEY(submitted_by_user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS password_reset_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                account_kind TEXT NOT NULL,
                account_id INTEGER NOT NULL,
                token TEXT UNIQUE NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                requested_at TEXT DEFAULT CURRENT_TIMESTAMP,
                expires_at TEXT NOT NULL,
                used_at TEXT DEFAULT '',
                requester_ip TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT '',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS email_settings_profile (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                smtp_email TEXT NOT NULL DEFAULT '',
                smtp_host TEXT NOT NULL DEFAULT 'smtp.gmail.com',
                smtp_port TEXT NOT NULL DEFAULT '587',
                smtp_username TEXT NOT NULL DEFAULT '',
                smtp_sender_name TEXT NOT NULL DEFAULT 'LedgerFlow',
                smtp_password_enc TEXT NOT NULL DEFAULT '',
                app_base_url TEXT NOT NULL DEFAULT '',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_by_user_id INTEGER,
                last_tested_at TEXT DEFAULT '',
                last_test_status TEXT DEFAULT '',
                last_test_recipient TEXT DEFAULT '',
                last_test_error TEXT DEFAULT '',
                FOREIGN KEY(updated_by_user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS business_invites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                invited_email TEXT NOT NULL,
                invited_name TEXT DEFAULT '',
                token TEXT UNIQUE NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                invite_error TEXT DEFAULT '',
                created_by_user_id INTEGER NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                expires_at TEXT NOT NULL,
                used_at TEXT DEFAULT '',
                accepted_user_id INTEGER,
                followup_sent_at TEXT DEFAULT '',
                followup_status TEXT DEFAULT 'pending',
                followup_error TEXT DEFAULT '',
                FOREIGN KEY(client_id) REFERENCES clients(id),
                FOREIGN KEY(created_by_user_id) REFERENCES users(id),
                FOREIGN KEY(accepted_user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS account_activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER,
                account_type TEXT DEFAULT 'login',
                account_email TEXT DEFAULT '',
                account_name TEXT DEFAULT '',
                created_by_user_id INTEGER,
                status TEXT DEFAULT 'created',
                detail TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(client_id) REFERENCES clients(id),
                FOREIGN KEY(created_by_user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS email_delivery_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER,
                email_type TEXT DEFAULT '',
                recipient_email TEXT DEFAULT '',
                recipient_name TEXT DEFAULT '',
                subject TEXT DEFAULT '',
                body_text TEXT DEFAULT '',
                body_html TEXT DEFAULT '',
                status TEXT DEFAULT 'sent',
                error_message TEXT DEFAULT '',
                created_by_user_id INTEGER,
                related_invite_id INTEGER,
                related_user_id INTEGER,
                tracking_token TEXT DEFAULT '',
                opened_at TEXT DEFAULT '',
                open_count INTEGER NOT NULL DEFAULT 0,
                clicked_at TEXT DEFAULT '',
                click_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(client_id) REFERENCES clients(id),
                FOREIGN KEY(created_by_user_id) REFERENCES users(id),
                FOREIGN KEY(related_invite_id) REFERENCES business_invites(id),
                FOREIGN KEY(related_user_id) REFERENCES users(id)
            );
            """
        )

        # Migrate business_invites table if an older CHECK constraint exists that blocks new statuses
        row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='business_invites'").fetchone()
        if row and row['sql'] and 'CHECK(status' in row['sql']:
            conn.execute('ALTER TABLE business_invites RENAME TO business_invites_old')
            conn.execute(
                """CREATE TABLE business_invites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER NOT NULL,
                    invited_email TEXT NOT NULL,
                    invited_name TEXT DEFAULT '',
                    token TEXT UNIQUE NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    invite_error TEXT DEFAULT '',
                    created_by_user_id INTEGER NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    expires_at TEXT NOT NULL,
                    used_at TEXT DEFAULT '',
                    accepted_user_id INTEGER,
                    followup_sent_at TEXT DEFAULT '',
                    followup_status TEXT DEFAULT 'pending',
                    followup_error TEXT DEFAULT '',
                    FOREIGN KEY(client_id) REFERENCES clients(id),
                    FOREIGN KEY(created_by_user_id) REFERENCES users(id),
                    FOREIGN KEY(accepted_user_id) REFERENCES users(id)
                )"""
            )
            conn.execute(
                """INSERT INTO business_invites (id, client_id, invited_email, invited_name, token, status, created_by_user_id, created_at, expires_at, used_at, accepted_user_id)
                   SELECT id, client_id, invited_email, invited_name, token, status, created_by_user_id, created_at, expires_at, used_at, accepted_user_id
                   FROM business_invites_old"""
            )
            conn.execute('DROP TABLE business_invites_old')
            conn.commit()
        ensure_column(conn, 'workers', 'phone', "TEXT DEFAULT ''")
        ensure_column(conn, 'workers', 'email', "TEXT DEFAULT ''")
        ensure_column(conn, 'workers', 'address', "TEXT DEFAULT ''")
        ensure_column(conn, 'workers', 'pay_notes', "TEXT DEFAULT ''")
        ensure_column(conn, 'workers', 'payout_preference', "TEXT DEFAULT 'paper_check'")
        ensure_column(conn, 'workers', 'deposit_bank_name', "TEXT DEFAULT ''")
        ensure_column(conn, 'workers', 'deposit_account_holder_name', "TEXT DEFAULT ''")
        ensure_column(conn, 'workers', 'deposit_account_type', "TEXT DEFAULT 'checking'")
        ensure_column(conn, 'workers', 'deposit_account_last4', "TEXT DEFAULT ''")
        ensure_column(conn, 'workers', 'deposit_routing_number_enc', "TEXT DEFAULT ''")
        ensure_column(conn, 'workers', 'deposit_account_number_enc', "TEXT DEFAULT ''")
        ensure_column(conn, 'workers', 'zelle_contact', "TEXT DEFAULT ''")
        ensure_column(conn, 'worker_payments', 'payment_method', "TEXT DEFAULT 'direct_deposit'")
        ensure_column(conn, 'worker_payments', 'payment_status', "TEXT DEFAULT 'paid'")
        ensure_column(conn, 'worker_payments', 'reference_number', "TEXT DEFAULT ''")
        ensure_column(conn, 'worker_policy_notices', 'is_active', 'INTEGER NOT NULL DEFAULT 1')
        ensure_column(conn, 'worker_policy_notices', 'updated_at', "TEXT DEFAULT CURRENT_TIMESTAMP")
        ensure_column(conn, 'users', 'last_seen_at', "TEXT DEFAULT ''")
        ensure_column(conn, 'users', 'preferred_language', "TEXT DEFAULT 'en'")
        ensure_column(conn, 'internal_messages', 'recipient_user_id', 'INTEGER')
        ensure_column(conn, 'admin_calendar_reminders', 'admin_user_id', 'INTEGER')
        ensure_column(conn, 'admin_calendar_reminders', 'reminder_type', "TEXT DEFAULT ''")
        ensure_column(conn, 'admin_calendar_reminders', 'reminder_date', "TEXT DEFAULT ''")
        ensure_column(conn, 'admin_calendar_reminders', 'note', "TEXT DEFAULT ''")
        ensure_column(conn, 'admin_calendar_reminders', 'created_at', "TEXT DEFAULT (datetime('now'))")
        ensure_column(conn, 'admin_todo_items', 'admin_user_id', 'INTEGER')
        ensure_column(conn, 'admin_todo_items', 'title', "TEXT DEFAULT ''")
        ensure_column(conn, 'admin_todo_items', 'due_date', "TEXT DEFAULT ''")
        ensure_column(conn, 'admin_todo_items', 'priority', "TEXT DEFAULT 'medium'")
        ensure_column(conn, 'admin_todo_items', 'is_completed', 'INTEGER NOT NULL DEFAULT 0')
        ensure_column(conn, 'admin_todo_items', 'created_at', "TEXT DEFAULT (datetime('now'))")
        ensure_column(conn, 'admin_todo_items', 'completed_at', "TEXT DEFAULT ''")
        ensure_column(conn, 'business_calendar_reminders', 'client_id', 'INTEGER')
        ensure_column(conn, 'business_calendar_reminders', 'created_by_user_id', 'INTEGER')
        ensure_column(conn, 'business_calendar_reminders', 'reminder_type', "TEXT DEFAULT ''")
        ensure_column(conn, 'business_calendar_reminders', 'reminder_date', "TEXT DEFAULT ''")
        ensure_column(conn, 'business_calendar_reminders', 'note', "TEXT DEFAULT ''")
        ensure_column(conn, 'business_calendar_reminders', 'created_at', "TEXT DEFAULT (datetime('now'))")



        ensure_column(conn, 'internal_messages', 'is_read', 'INTEGER DEFAULT 0')
        ensure_column(conn, 'workers', 'hire_date', "TEXT DEFAULT ''")
        ensure_column(conn, 'workers', 'payroll_frequency', "TEXT DEFAULT 'weekly'")
        ensure_column(conn, 'workers', 'role_classification', "TEXT DEFAULT ''")
        ensure_column(conn, 'workers', 'status', "TEXT DEFAULT 'active'")
        ensure_column(conn, 'workers', 'termination_date', "TEXT DEFAULT ''")
        ensure_column(conn, 'workers', 'termination_cause', "TEXT DEFAULT ''")
        ensure_column(conn, 'workers', 'portal_password_hash', "TEXT DEFAULT ''")
        ensure_column(conn, 'workers', 'portal_access_enabled', 'INTEGER NOT NULL DEFAULT 1')
        ensure_column(conn, 'workers', 'portal_last_seen_at', "TEXT DEFAULT ''")
        ensure_column(conn, 'workers', 'portal_approval_status', "TEXT DEFAULT 'approved'")
        ensure_column(conn, 'workers', 'portal_requested_at', "TEXT DEFAULT ''")
        ensure_column(conn, 'workers', 'portal_approved_at', "TEXT DEFAULT ''")
        ensure_column(conn, 'workers', 'portal_approved_by', 'INTEGER')
        ensure_column(conn, 'workers', 'created_by_user_id', 'INTEGER')
        ensure_column(conn, 'workers', 'updated_at', "TEXT DEFAULT ''")
        ensure_column(conn, 'workers', 'updated_by_user_id', 'INTEGER')
        ensure_column(conn, 'workers', 'preferred_language', "TEXT DEFAULT 'en'")
        ensure_column(conn, 'clients', 'preferred_language', "TEXT DEFAULT 'en'")
        ensure_column(conn, 'clients', 'business_type', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'business_category', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'business_specialty', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'owner_contacts', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'job_scope_summary', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'eftps_status', "TEXT DEFAULT 'Not Enrolled'")
        ensure_column(conn, 'clients', 'eftps_login_reference', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'filing_type', "TEXT DEFAULT 'Both'")
        ensure_column(conn, 'clients', 'bank_name', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'bank_account_nickname', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'bank_account_last4', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'bank_account_holder_name', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'bank_account_number', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'bank_routing_number', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'credit_card_nickname', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'credit_card_last4', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'credit_card_holder_name', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'credit_card_number', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'payroll_contact_name', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'payroll_contact_phone', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'payroll_contact_email', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'state_tax_id', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'service_level', "TEXT DEFAULT 'self_service'")
        ensure_column(conn, 'clients', 'access_service_level', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'access_override_note', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'subscription_plan_code', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'subscription_status', "TEXT DEFAULT 'inactive'")
        ensure_column(conn, 'clients', 'subscription_amount', 'REAL NOT NULL DEFAULT 0')
        ensure_column(conn, 'clients', 'subscription_interval', "TEXT DEFAULT 'monthly'")
        ensure_column(conn, 'clients', 'subscription_autopay_enabled', 'INTEGER NOT NULL DEFAULT 0')
        ensure_column(conn, 'clients', 'subscription_next_billing_date', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'subscription_started_at', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'subscription_canceled_at', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'subscription_paused_at', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'onboarding_status', "TEXT DEFAULT 'completed'")
        ensure_column(conn, 'clients', 'onboarding_started_at', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'onboarding_completed_at', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'onboarding_completed_by_user_id', 'INTEGER')
        ensure_column(conn, 'clients', 'record_status', "TEXT DEFAULT 'active'")
        ensure_column(conn, 'clients', 'archive_reason', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'archived_at', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'archived_by_user_id', 'INTEGER')
        ensure_column(conn, 'clients', 'reactivated_at', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'default_payment_method_label', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'default_payment_method_status', "TEXT DEFAULT 'missing'")
        ensure_column(conn, 'clients', 'backup_payment_method_label', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'billing_notes', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'created_by_user_id', 'INTEGER')
        ensure_column(conn, 'clients', 'updated_at', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'updated_by_user_id', 'INTEGER')
        conn.execute("UPDATE clients SET onboarding_status='completed' WHERE COALESCE(onboarding_status,'')=''")
        conn.execute("UPDATE clients SET record_status='active' WHERE COALESCE(record_status,'')=''")
        conn.execute("UPDATE clients SET updated_at=created_at WHERE COALESCE(updated_at,'')=''")
        conn.execute("UPDATE clients SET preferred_language='en' WHERE COALESCE(preferred_language,'')=''")
        conn.execute("UPDATE workers SET updated_at=created_at WHERE COALESCE(updated_at,'')=''")
        conn.execute("UPDATE users SET preferred_language='en' WHERE COALESCE(preferred_language,'')=''")
        conn.execute("UPDATE workers SET preferred_language='en' WHERE COALESCE(preferred_language,'')=''")
        ensure_column(conn, 'business_payment_items', 'payment_type', "TEXT DEFAULT 'other'")
        ensure_column(conn, 'business_payment_items', 'is_admin_fee', "INTEGER NOT NULL DEFAULT 1")
        ensure_column(conn, 'business_payment_items', 'collection_method', "TEXT DEFAULT 'send_payment_request'")
        ensure_column(conn, 'business_payment_items', 'public_payment_link', "TEXT DEFAULT ''")
        ensure_column(conn, 'business_payment_items', 'payment_instructions', "TEXT DEFAULT ''")
        ensure_column(conn, 'business_payment_items', 'cancellation_note', "TEXT DEFAULT ''")
        ensure_column(conn, 'business_payment_items', 'archived_at', "TEXT DEFAULT ''")
        ensure_column(conn, 'business_payment_methods', 'method_type', "TEXT DEFAULT 'other'")
        ensure_column(conn, 'business_payment_methods', 'label', "TEXT DEFAULT ''")
        ensure_column(conn, 'business_payment_methods', 'status', "TEXT DEFAULT 'active'")
        ensure_column(conn, 'business_payment_methods', 'is_default', 'INTEGER NOT NULL DEFAULT 0')
        ensure_column(conn, 'business_payment_methods', 'is_backup', 'INTEGER NOT NULL DEFAULT 0')
        ensure_column(conn, 'business_payment_methods', 'holder_name', "TEXT DEFAULT ''")
        ensure_column(conn, 'business_payment_methods', 'brand_name', "TEXT DEFAULT ''")
        ensure_column(conn, 'business_payment_methods', 'account_last4', "TEXT DEFAULT ''")
        ensure_column(conn, 'business_payment_methods', 'expiry_display', "TEXT DEFAULT ''")
        ensure_column(conn, 'business_payment_methods', 'account_type', "TEXT DEFAULT ''")
        ensure_column(conn, 'business_payment_methods', 'card_number_enc', "TEXT DEFAULT ''")
        ensure_column(conn, 'business_payment_methods', 'routing_number_enc', "TEXT DEFAULT ''")
        ensure_column(conn, 'business_payment_methods', 'account_number_enc', "TEXT DEFAULT ''")
        ensure_column(conn, 'business_payment_methods', 'details_note', "TEXT DEFAULT ''")
        ensure_column(conn, 'business_payment_methods', 'created_by_user_id', 'INTEGER')
        ensure_column(conn, 'business_payment_methods', 'created_at', "TEXT DEFAULT CURRENT_TIMESTAMP")
        ensure_column(conn, 'business_payment_methods', 'updated_at', "TEXT DEFAULT CURRENT_TIMESTAMP")
        ensure_column(conn, 'business_invites', 'invite_error', "TEXT DEFAULT ''")
        ensure_column(conn, 'business_invites', 'invite_kind', "TEXT DEFAULT 'business_access'")
        ensure_column(conn, 'business_invites', 'trial_days', 'INTEGER NOT NULL DEFAULT 0')
        ensure_column(conn, 'business_invites', 'followup_sent_at', "TEXT DEFAULT ''")
        ensure_column(conn, 'business_invites', 'followup_status', "TEXT DEFAULT 'pending'")
        ensure_column(conn, 'business_invites', 'followup_error', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'trial_offer_days', 'INTEGER NOT NULL DEFAULT 0')
        ensure_column(conn, 'clients', 'trial_started_at', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'trial_ends_at', "TEXT DEFAULT ''")
        ensure_column(conn, 'email_delivery_log', 'tracking_token', "TEXT DEFAULT ''")
        ensure_column(conn, 'email_delivery_log', 'opened_at', "TEXT DEFAULT ''")
        ensure_column(conn, 'email_delivery_log', 'open_count', 'INTEGER NOT NULL DEFAULT 0')
        ensure_column(conn, 'email_delivery_log', 'clicked_at', "TEXT DEFAULT ''")
        ensure_column(conn, 'email_delivery_log', 'click_count', 'INTEGER NOT NULL DEFAULT 0')
        ensure_column(conn, 'invoices', 'notes', "TEXT DEFAULT ''")
        ensure_column(conn, 'invoices', 'income_category', "TEXT DEFAULT 'service_income'")
        ensure_column(conn, 'invoices', 'sales_tax_amount', 'REAL NOT NULL DEFAULT 0')
        ensure_column(conn, 'invoices', 'sales_tax_paid', 'INTEGER NOT NULL DEFAULT 0')
        ensure_column(conn, 'invoices', 'record_kind', "TEXT NOT NULL DEFAULT 'income_record'")
        ensure_column(conn, 'invoices', 'invoice_title', "TEXT DEFAULT ''")
        ensure_column(conn, 'invoices', 'recipient_email', "TEXT DEFAULT ''")
        ensure_column(conn, 'invoices', 'invoice_total_amount', 'REAL NOT NULL DEFAULT 0')
        ensure_column(conn, 'invoices', 'due_date', "TEXT DEFAULT ''")
        ensure_column(conn, 'invoices', 'estimate_expiration_date', "TEXT DEFAULT ''")
        ensure_column(conn, 'invoices', 'invoice_status', "TEXT NOT NULL DEFAULT 'draft'")
        ensure_column(conn, 'invoices', 'public_invoice_token', "TEXT DEFAULT ''")
        ensure_column(conn, 'invoices', 'public_payment_link', "TEXT DEFAULT ''")
        ensure_column(conn, 'invoices', 'sent_at', "TEXT DEFAULT ''")
        ensure_column(conn, 'invoices', 'last_reminder_at', "TEXT DEFAULT ''")
        ensure_column(conn, 'invoices', 'reminder_count', 'INTEGER NOT NULL DEFAULT 0')
        ensure_column(conn, 'invoices', 'customer_viewed_at', "TEXT DEFAULT ''")
        ensure_column(conn, 'invoices', 'customer_paid_at', "TEXT DEFAULT ''")
        ensure_column(conn, 'invoices', 'approved_at', "TEXT DEFAULT ''")
        ensure_column(conn, 'invoices', 'declined_at', "TEXT DEFAULT ''")
        ensure_column(conn, 'invoices', 'converted_invoice_id', 'INTEGER')
        ensure_column(conn, 'invoices', 'customer_contact_id', 'INTEGER')
        ensure_column(conn, 'invoices', 'payment_note', "TEXT DEFAULT ''")
        ensure_column(conn, 'customer_contacts', 'customer_phone', "TEXT DEFAULT ''")
        ensure_column(conn, 'customer_contacts', 'customer_address', "TEXT DEFAULT ''")
        ensure_column(conn, 'customer_contacts', 'customer_notes', "TEXT DEFAULT ''")
        ensure_column(conn, 'customer_contacts', 'status', "TEXT DEFAULT 'active'")
        ensure_column(conn, 'customer_contacts', 'recurring_frequency', "TEXT DEFAULT ''")
        ensure_column(conn, 'customer_contacts', 'recurring_weekday', "TEXT DEFAULT ''")
        ensure_column(conn, 'customer_contacts', 'recurring_start_date', "TEXT DEFAULT ''")
        ensure_column(conn, 'customer_contacts', 'recurring_end_date', "TEXT DEFAULT ''")
        ensure_column(conn, 'customer_contacts', 'recurring_job_name', "TEXT DEFAULT ''")
        ensure_column(conn, 'customer_contacts', 'recurring_scope', "TEXT DEFAULT ''")
        ensure_column(conn, 'customer_contacts', 'recurring_start_time', "TEXT DEFAULT ''")
        ensure_column(conn, 'customer_contacts', 'recurring_end_time', "TEXT DEFAULT ''")
        ensure_column(conn, 'customer_contacts', 'recurring_estimated_duration', "TEXT DEFAULT ''")
        ensure_column(conn, 'customer_contacts', 'recurring_expected_amount', 'REAL DEFAULT 0')
        ensure_column(conn, 'customer_contacts', 'auto_add_to_calendar', 'INTEGER NOT NULL DEFAULT 0')
        ensure_column(conn, 'customer_contacts', 'created_by_user_id', 'INTEGER')
        ensure_column(conn, 'customer_contacts', 'updated_by_user_id', 'INTEGER')
        ensure_column(conn, 'customer_contacts', 'created_at', "TEXT DEFAULT CURRENT_TIMESTAMP")
        ensure_column(conn, 'customer_contacts', 'updated_at', "TEXT DEFAULT CURRENT_TIMESTAMP")
        ensure_column(conn, 'work_schedule_entries', 'customer_contact_id', 'INTEGER')
        ensure_column(conn, 'work_schedule_entries', 'auto_generated', 'INTEGER NOT NULL DEFAULT 0')
        ensure_column(conn, 'work_schedule_entries', 'expected_amount', 'REAL DEFAULT 0')

        conn.executescript(
            '''
            CREATE TABLE IF NOT EXISTS service_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                default_duration_minutes INTEGER NOT NULL DEFAULT 120,
                default_priority TEXT DEFAULT 'normal',
                default_crew_size INTEGER NOT NULL DEFAULT 1,
                color_token TEXT DEFAULT '#72819A',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(client_id, name),
                FOREIGN KEY(client_id) REFERENCES clients(id)
            );
            CREATE TABLE IF NOT EXISTS service_locations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                customer_contact_id INTEGER,
                location_name TEXT DEFAULT '',
                address_line1 TEXT DEFAULT '',
                city TEXT DEFAULT '',
                state TEXT DEFAULT '',
                postal_code TEXT DEFAULT '',
                access_notes TEXT DEFAULT '',
                gate_code TEXT DEFAULT '',
                parking_notes TEXT DEFAULT '',
                location_notes TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(client_id) REFERENCES clients(id),
                FOREIGN KEY(customer_contact_id) REFERENCES customer_contacts(id)
            );
            CREATE TABLE IF NOT EXISTS job_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                service_type_id INTEGER,
                name TEXT NOT NULL,
                default_title TEXT DEFAULT '',
                default_duration_minutes INTEGER NOT NULL DEFAULT 120,
                default_priority TEXT DEFAULT 'normal',
                default_tags TEXT DEFAULT '',
                default_notes TEXT DEFAULT '',
                default_crew_size INTEGER NOT NULL DEFAULT 1,
                checklist_text TEXT DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(client_id) REFERENCES clients(id),
                FOREIGN KEY(service_type_id) REFERENCES service_types(id)
            );
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                legacy_schedule_entry_id INTEGER UNIQUE,
                customer_contact_id INTEGER,
                service_location_id INTEGER,
                service_type_id INTEGER,
                template_id INTEGER,
                created_by_user_id INTEGER,
                updated_by_user_id INTEGER,
                title TEXT NOT NULL,
                customer_name TEXT DEFAULT '',
                customer_reference TEXT DEFAULT '',
                service_type_name TEXT DEFAULT '',
                priority TEXT DEFAULT 'normal',
                status TEXT DEFAULT 'unscheduled',
                field_progress_status TEXT DEFAULT 'not_started',
                tags TEXT DEFAULT '',
                service_address TEXT DEFAULT '',
                city TEXT DEFAULT '',
                state TEXT DEFAULT '',
                postal_code TEXT DEFAULT '',
                scheduled_start TEXT DEFAULT '',
                scheduled_end TEXT DEFAULT '',
                estimated_duration_minutes INTEGER NOT NULL DEFAULT 0,
                notes_summary TEXT DEFAULT '',
                internal_notes TEXT DEFAULT '',
                dispatch_notes TEXT DEFAULT '',
                completion_notes TEXT DEFAULT '',
                recurrence_rule TEXT DEFAULT '',
                is_recurring INTEGER NOT NULL DEFAULT 0,
                cancellation_reason TEXT DEFAULT '',
                issue_flag INTEGER NOT NULL DEFAULT 0,
                requires_revisit INTEGER NOT NULL DEFAULT 0,
                completed_at TEXT DEFAULT '',
                last_progress_at TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(client_id) REFERENCES clients(id),
                FOREIGN KEY(customer_contact_id) REFERENCES customer_contacts(id),
                FOREIGN KEY(service_location_id) REFERENCES service_locations(id),
                FOREIGN KEY(service_type_id) REFERENCES service_types(id),
                FOREIGN KEY(template_id) REFERENCES job_templates(id),
                FOREIGN KEY(created_by_user_id) REFERENCES users(id),
                FOREIGN KEY(updated_by_user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS job_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                worker_id INTEGER NOT NULL,
                assignment_role TEXT DEFAULT 'crew_member',
                assigned_at TEXT DEFAULT CURRENT_TIMESTAMP,
                assigned_by_user_id INTEGER,
                status TEXT DEFAULT 'assigned',
                sort_order INTEGER NOT NULL DEFAULT 0,
                UNIQUE(job_id, worker_id),
                FOREIGN KEY(job_id) REFERENCES jobs(id),
                FOREIGN KEY(worker_id) REFERENCES workers(id),
                FOREIGN KEY(assigned_by_user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS worker_availability (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                worker_id INTEGER NOT NULL,
                client_id INTEGER NOT NULL,
                available_date TEXT NOT NULL,
                start_time TEXT DEFAULT '',
                end_time TEXT DEFAULT '',
                availability_status TEXT DEFAULT 'available',
                note TEXT DEFAULT '',
                created_by_user_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(worker_id) REFERENCES workers(id),
                FOREIGN KEY(client_id) REFERENCES clients(id),
                FOREIGN KEY(created_by_user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS job_activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                job_id INTEGER NOT NULL,
                actor_type TEXT DEFAULT 'system',
                actor_id INTEGER,
                event_type TEXT DEFAULT 'updated',
                event_text TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(client_id) REFERENCES clients(id),
                FOREIGN KEY(job_id) REFERENCES jobs(id)
            );
            CREATE TABLE IF NOT EXISTS job_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                client_id INTEGER NOT NULL,
                note_type TEXT DEFAULT 'internal',
                body TEXT NOT NULL,
                created_by_user_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(job_id) REFERENCES jobs(id),
                FOREIGN KEY(client_id) REFERENCES clients(id),
                FOREIGN KEY(created_by_user_id) REFERENCES users(id)
            );
            '''
        )
        ensure_column(conn, 'workers', 'worker_role', "TEXT DEFAULT ''")
        ensure_column(conn, 'workers', 'crew_label', "TEXT DEFAULT ''")
        ensure_column(conn, 'workers', 'skill_tags', "TEXT DEFAULT ''")
        ensure_column(conn, 'workers', 'availability_baseline', "TEXT DEFAULT ''")
        ensure_column(conn, 'service_types', 'description', "TEXT DEFAULT ''")
        ensure_column(conn, 'service_types', 'default_duration_minutes', 'INTEGER NOT NULL DEFAULT 120')
        ensure_column(conn, 'service_types', 'default_priority', "TEXT DEFAULT 'normal'")
        ensure_column(conn, 'service_types', 'default_crew_size', 'INTEGER NOT NULL DEFAULT 1')
        ensure_column(conn, 'service_types', 'color_token', "TEXT DEFAULT '#72819A'")
        ensure_column(conn, 'service_types', 'is_active', 'INTEGER NOT NULL DEFAULT 1')
        ensure_column(conn, 'service_types', 'created_at', "TEXT DEFAULT CURRENT_TIMESTAMP")
        ensure_column(conn, 'service_types', 'updated_at', "TEXT DEFAULT CURRENT_TIMESTAMP")
        ensure_column(conn, 'service_locations', 'customer_contact_id', 'INTEGER')
        ensure_column(conn, 'service_locations', 'location_name', "TEXT DEFAULT ''")
        ensure_column(conn, 'service_locations', 'address_line1', "TEXT DEFAULT ''")
        ensure_column(conn, 'service_locations', 'city', "TEXT DEFAULT ''")
        ensure_column(conn, 'service_locations', 'state', "TEXT DEFAULT ''")
        ensure_column(conn, 'service_locations', 'postal_code', "TEXT DEFAULT ''")
        ensure_column(conn, 'service_locations', 'access_notes', "TEXT DEFAULT ''")
        ensure_column(conn, 'service_locations', 'gate_code', "TEXT DEFAULT ''")
        ensure_column(conn, 'service_locations', 'parking_notes', "TEXT DEFAULT ''")
        ensure_column(conn, 'service_locations', 'location_notes', "TEXT DEFAULT ''")
        ensure_column(conn, 'service_locations', 'created_at', "TEXT DEFAULT CURRENT_TIMESTAMP")
        ensure_column(conn, 'service_locations', 'updated_at', "TEXT DEFAULT CURRENT_TIMESTAMP")
        ensure_column(conn, 'job_templates', 'service_type_id', 'INTEGER')
        ensure_column(conn, 'job_templates', 'default_title', "TEXT DEFAULT ''")
        ensure_column(conn, 'job_templates', 'default_duration_minutes', 'INTEGER NOT NULL DEFAULT 120')
        ensure_column(conn, 'job_templates', 'default_priority', "TEXT DEFAULT 'normal'")
        ensure_column(conn, 'job_templates', 'default_tags', "TEXT DEFAULT ''")
        ensure_column(conn, 'job_templates', 'default_notes', "TEXT DEFAULT ''")
        ensure_column(conn, 'job_templates', 'default_crew_size', 'INTEGER NOT NULL DEFAULT 1')
        ensure_column(conn, 'job_templates', 'checklist_text', "TEXT DEFAULT ''")
        ensure_column(conn, 'job_templates', 'is_active', 'INTEGER NOT NULL DEFAULT 1')
        ensure_column(conn, 'job_templates', 'created_at', "TEXT DEFAULT CURRENT_TIMESTAMP")
        ensure_column(conn, 'job_templates', 'updated_at', "TEXT DEFAULT CURRENT_TIMESTAMP")
        ensure_column(conn, 'jobs', 'legacy_schedule_entry_id', 'INTEGER')
        ensure_column(conn, 'jobs', 'customer_contact_id', 'INTEGER')
        ensure_column(conn, 'jobs', 'service_location_id', 'INTEGER')
        ensure_column(conn, 'jobs', 'service_type_id', 'INTEGER')
        ensure_column(conn, 'jobs', 'template_id', 'INTEGER')
        ensure_column(conn, 'jobs', 'created_by_user_id', 'INTEGER')
        ensure_column(conn, 'jobs', 'updated_by_user_id', 'INTEGER')
        ensure_column(conn, 'jobs', 'customer_name', "TEXT DEFAULT ''")
        ensure_column(conn, 'jobs', 'customer_reference', "TEXT DEFAULT ''")
        ensure_column(conn, 'jobs', 'service_type_name', "TEXT DEFAULT ''")
        ensure_column(conn, 'jobs', 'priority', "TEXT DEFAULT 'normal'")
        ensure_column(conn, 'jobs', 'status', "TEXT DEFAULT 'unscheduled'")
        ensure_column(conn, 'jobs', 'field_progress_status', "TEXT DEFAULT 'not_started'")
        ensure_column(conn, 'jobs', 'tags', "TEXT DEFAULT ''")
        ensure_column(conn, 'jobs', 'service_address', "TEXT DEFAULT ''")
        ensure_column(conn, 'jobs', 'city', "TEXT DEFAULT ''")
        ensure_column(conn, 'jobs', 'state', "TEXT DEFAULT ''")
        ensure_column(conn, 'jobs', 'postal_code', "TEXT DEFAULT ''")
        ensure_column(conn, 'jobs', 'scheduled_start', "TEXT DEFAULT ''")
        ensure_column(conn, 'jobs', 'scheduled_end', "TEXT DEFAULT ''")
        ensure_column(conn, 'jobs', 'estimated_duration_minutes', 'INTEGER NOT NULL DEFAULT 0')
        ensure_column(conn, 'jobs', 'notes_summary', "TEXT DEFAULT ''")
        ensure_column(conn, 'jobs', 'internal_notes', "TEXT DEFAULT ''")
        ensure_column(conn, 'jobs', 'dispatch_notes', "TEXT DEFAULT ''")
        ensure_column(conn, 'jobs', 'completion_notes', "TEXT DEFAULT ''")
        ensure_column(conn, 'jobs', 'recurrence_rule', "TEXT DEFAULT ''")
        ensure_column(conn, 'jobs', 'is_recurring', 'INTEGER NOT NULL DEFAULT 0')
        ensure_column(conn, 'jobs', 'cancellation_reason', "TEXT DEFAULT ''")
        ensure_column(conn, 'jobs', 'issue_flag', 'INTEGER NOT NULL DEFAULT 0')
        ensure_column(conn, 'jobs', 'requires_revisit', 'INTEGER NOT NULL DEFAULT 0')
        ensure_column(conn, 'jobs', 'completed_at', "TEXT DEFAULT ''")
        ensure_column(conn, 'jobs', 'last_progress_at', "TEXT DEFAULT ''")
        ensure_column(conn, 'jobs', 'created_at', "TEXT DEFAULT CURRENT_TIMESTAMP")
        ensure_column(conn, 'jobs', 'updated_at', "TEXT DEFAULT CURRENT_TIMESTAMP")
        ensure_column(conn, 'job_assignments', 'assignment_role', "TEXT DEFAULT 'crew_member'")
        ensure_column(conn, 'job_assignments', 'assigned_at', "TEXT DEFAULT CURRENT_TIMESTAMP")
        ensure_column(conn, 'job_assignments', 'assigned_by_user_id', 'INTEGER')
        ensure_column(conn, 'job_assignments', 'status', "TEXT DEFAULT 'assigned'")
        ensure_column(conn, 'job_assignments', 'sort_order', 'INTEGER NOT NULL DEFAULT 0')
        ensure_column(conn, 'worker_availability', 'client_id', 'INTEGER')
        ensure_column(conn, 'worker_availability', 'available_date', "TEXT DEFAULT ''")
        ensure_column(conn, 'worker_availability', 'start_time', "TEXT DEFAULT ''")
        ensure_column(conn, 'worker_availability', 'end_time', "TEXT DEFAULT ''")
        ensure_column(conn, 'worker_availability', 'availability_status', "TEXT DEFAULT 'available'")
        ensure_column(conn, 'worker_availability', 'note', "TEXT DEFAULT ''")
        ensure_column(conn, 'worker_availability', 'created_by_user_id', 'INTEGER')
        ensure_column(conn, 'worker_availability', 'created_at', "TEXT DEFAULT CURRENT_TIMESTAMP")
        ensure_column(conn, 'worker_availability', 'updated_at', "TEXT DEFAULT CURRENT_TIMESTAMP")
        ensure_column(conn, 'job_activity_log', 'client_id', 'INTEGER')
        ensure_column(conn, 'job_activity_log', 'actor_type', "TEXT DEFAULT 'system'")
        ensure_column(conn, 'job_activity_log', 'actor_id', 'INTEGER')
        ensure_column(conn, 'job_activity_log', 'event_type', "TEXT DEFAULT 'updated'")
        ensure_column(conn, 'job_activity_log', 'event_text', "TEXT DEFAULT ''")
        ensure_column(conn, 'job_activity_log', 'created_at', "TEXT DEFAULT CURRENT_TIMESTAMP")
        ensure_column(conn, 'job_notes', 'client_id', 'INTEGER')
        ensure_column(conn, 'job_notes', 'note_type', "TEXT DEFAULT 'internal'")
        ensure_column(conn, 'job_notes', 'body', "TEXT DEFAULT ''")
        ensure_column(conn, 'job_notes', 'created_by_user_id', 'INTEGER')
        ensure_column(conn, 'job_notes', 'created_at', "TEXT DEFAULT CURRENT_TIMESTAMP")
        conn.execute("UPDATE invoices SET record_kind='income_record' WHERE COALESCE(record_kind,'')=''")
        conn.execute("UPDATE invoices SET invoice_total_amount=COALESCE(invoice_total_amount,0)+paid_amount WHERE COALESCE(invoice_total_amount,0)=0")
        conn.execute("UPDATE invoices SET invoice_status='paid' WHERE record_kind='income_record' AND COALESCE(invoice_status,'') IN ('', 'draft')")
        conn.execute("UPDATE invoices SET invoice_status='paid' WHERE record_kind='customer_invoice' AND COALESCE(paid_amount,0) >= COALESCE(invoice_total_amount,0) AND COALESCE(invoice_total_amount,0) > 0")
        conn.execute("UPDATE invoices SET invoice_status='partial' WHERE record_kind='customer_invoice' AND COALESCE(paid_amount,0) > 0 AND COALESCE(paid_amount,0) < COALESCE(invoice_total_amount,0)")
        conn.execute("UPDATE invoices SET invoice_status='draft' WHERE record_kind='customer_invoice' AND COALESCE(invoice_status,'')=''")
        conn.execute("UPDATE invoices SET invoice_status='draft' WHERE record_kind='estimate' AND COALESCE(invoice_status,'')=''")

        # Initialize base URL from environment for invite links in production
        env_base_url = (os.environ.get('APP_BASE_URL') or os.environ.get('RENDER_EXTERNAL_URL') or '').strip().rstrip('/')
        if env_base_url:
            existing = conn.execute("SELECT value FROM app_settings WHERE key='app_base_url'").fetchone()
            if not existing or not (existing['value'] or '').strip():
                conn.execute("INSERT INTO app_settings (key, value) VALUES ('app_base_url', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP", (env_base_url,))

        for tax_year, values in DEFAULT_TAX_RULES.items():
            exists = conn.execute('SELECT tax_year FROM tax_rules WHERE tax_year=?', (tax_year,)).fetchone()
            if not exists:
                conn.execute('''
                    INSERT INTO tax_rules (
                        tax_year, social_security_rate_employee, social_security_rate_employer, social_security_wage_base,
                        medicare_rate_employee, medicare_rate_employer, additional_medicare_rate, additional_medicare_threshold,
                        standard_deduction_single, standard_deduction_married, standard_deduction_head,
                        brackets_single_json, brackets_married_json, brackets_head_json
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ''', (
                    tax_year, values['social_security_rate_employee'], values['social_security_rate_employer'], values['social_security_wage_base'],
                    values['medicare_rate_employee'], values['medicare_rate_employer'], values['additional_medicare_rate'], values['additional_medicare_threshold'],
                    values['standard_deduction_single'], values['standard_deduction_married'], values['standard_deduction_head'],
                    values['brackets_single_json'], values['brackets_married_json'], values['brackets_head_json']
                ))

        migrate_legacy_schedule_to_jobs(conn)

        conn.commit()


def admin_user_exists() -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT 1 FROM users WHERE role='admin' LIMIT 1").fetchone()
    return bool(row)


def current_user():
    uid = session.get('user_id')
    if not uid:
        return None
    with get_conn() as conn:
        return conn.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()


def current_worker():
    worker_id = session.get('worker_id')
    if not worker_id:
        return None
    try:
        with get_conn() as conn:
            row = conn.execute(
                '''SELECT w.*, c.business_name, c.contact_name business_contact_name, c.id client_id_value,
                          c.subscription_status client_subscription_status, c.record_status client_record_status
                   FROM workers w
                   JOIN clients c ON c.id = w.client_id
                   WHERE w.id=?''',
                (worker_id,)
        ).fetchone()
        if not row or not worker_portal_access_allowed(row):
            session.pop('worker_id', None)
            flash(translate_text('Team member portal access is no longer active.', normalize_language(session.get('preferred_language'))), 'error')
            return None
        return row
    except sqlite3.Error:
        session.pop('worker_id', None)
        return None


def production_import_enabled() -> bool:
    return IS_PRODUCTION and (os.environ.get('PRODUCTION_IMPORT_ENABLED') or '').strip().lower() in {'1', 'true', 'yes', 'on'}


def production_import_key() -> str:
    return (os.environ.get('PRODUCTION_IMPORT_KEY') or '').strip()


def production_import_allowed() -> bool:
    return production_import_enabled() and bool(production_import_key())


def allowed_migration_files() -> set[str]:
    return {'rds_core_web.db', 'email_runtime_config.json', '.local_secret_key'}


def migration_target_paths() -> dict[str, Path]:
    return {
        'rds_core_web.db': DB_PATH,
        'email_runtime_config.json': EMAIL_CONFIG_PATH,
        '.local_secret_key': DATA_DIR / '.local_secret_key',
    }


def backup_existing_migration_files() -> Path | None:
    targets = migration_target_paths()
    existing = [name for name, path in targets.items() if path.exists()]
    if not existing:
        return None
    backup_dir = DATA_DIR / f"pre_import_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    for name in existing:
        shutil.copy2(targets[name], backup_dir / name)
    return backup_dir


def apply_migration_bundle(bundle_path: Path) -> tuple[list[str], Path | None]:
    extracted: dict[str, bytes] = {}
    with zipfile.ZipFile(bundle_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            clean_name = Path(info.filename).name
            if clean_name in allowed_migration_files():
                extracted[clean_name] = archive.read(info)
    if 'rds_core_web.db' not in extracted:
        raise RuntimeError('Migration bundle must include rds_core_web.db.')
    backup_dir = backup_existing_migration_files()
    written: list[str] = []
    targets = migration_target_paths()
    for name, raw in extracted.items():
        target = targets[name]
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, 'wb') as fh:
            fh.write(raw)
        written.append(name)
    return written, backup_dir


def production_import_status_snapshot() -> dict:
    db_exists = DB_PATH.exists()
    admin_count = 0
    user_count = 0
    worker_count = 0
    client_count = 0
    db_error = ''
    if db_exists:
        try:
            with get_conn() as conn:
                admin_count = int(conn.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0] or 0)
                user_count = int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] or 0)
                worker_count = int(conn.execute("SELECT COUNT(*) FROM workers").fetchone()[0] or 0)
                client_count = int(conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0] or 0)
        except Exception as exc:
            db_error = str(exc)
    return {
        'data_dir': str(DATA_DIR),
        'db_path': str(DB_PATH),
        'email_config_path': str(EMAIL_CONFIG_PATH),
        'db_exists': db_exists,
        'db_size': DB_PATH.stat().st_size if db_exists else 0,
        'email_config_exists': EMAIL_CONFIG_PATH.exists(),
        'secret_key_exists': (DATA_DIR / '.local_secret_key').exists(),
        'admin_count': admin_count,
        'user_count': user_count,
        'worker_count': worker_count,
        'client_count': client_count,
        'database_path_env': (os.environ.get('DATABASE_PATH') or '').strip(),
        'data_dir_env': (os.environ.get('DATA_DIR') or '').strip(),
        'db_error': db_error,
    }


def current_language_code(user=None, worker=None, client=None) -> str:
    session_lang = normalize_language(session.get('preferred_language', ''))
    if session_lang != 'en' or session.get('preferred_language'):
        return session_lang
    if worker and (worker['preferred_language'] or '').strip():
        return normalize_language(worker['preferred_language'])
    if user and (user['preferred_language'] or '').strip():
        return normalize_language(user['preferred_language'])
    if client and (client['preferred_language'] or '').strip():
        return normalize_language(client['preferred_language'])
    return 'en'


def seed_guest_language(preferred_language: str | None) -> str:
    if session.get('user_id') or session.get('worker_id'):
        return normalize_language(session.get('preferred_language'))
    if session.get('language_override_active'):
        return normalize_language(session.get('preferred_language'))
    language = normalize_language(preferred_language)
    session['preferred_language'] = language
    return language


def safe_next_path(path: str | None, fallback: str = '/main-portal') -> str:
    candidate = (path or '').strip()
    if candidate.startswith('/') and not candidate.startswith('//'):
        return candidate
    return fallback


def login_required(fn):
    @wraps(fn)
    def wrap(*args, **kwargs):
        user = current_user()
        if not user:
            return redirect(url_for('login'))
        if request.endpoint != 'business_comeback':
            issue = client_access_issue_for_user(user)
            if issue:
                return redirect(url_for('business_comeback'))
        return fn(*args, **kwargs)
    return wrap


def admin_required(fn):
    @wraps(fn)
    def wrap(*args, **kwargs):
        user = current_user()
        if not user:
            return redirect(url_for('login'))
        if user['role'] != 'admin':
            abort(403)
        return fn(*args, **kwargs)
    return wrap


def worker_login_required(fn):
    @wraps(fn)
    def wrap(*args, **kwargs):
        if not current_worker():
            return redirect(url_for('worker_login'))
        return fn(*args, **kwargs)
    return wrap


def visible_client_ids(user, *, include_non_active: bool = False):
    if user['role'] == 'admin':
        with get_conn() as conn:
            if include_non_active:
                rows = conn.execute("SELECT id FROM clients WHERE COALESCE(record_status,'active')<>'archived' ORDER BY business_name").fetchall()
            else:
                rows = conn.execute("SELECT id FROM clients WHERE COALESCE(record_status,'active')='active' ORDER BY business_name").fetchall()
            return [r['id'] for r in rows]
    return [user['client_id']] if user['client_id'] else []


def allowed_client(user, client_id):
    return client_id in visible_client_ids(user)


def parse_date(value):
    if not value:
        return None
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y'):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def between_clause(column: str, start_date: str | None, end_date: str | None):
    clauses, params = [], []
    if start_date:
        clauses.append(f"{column} >= ?")
        params.append(start_date)
    if end_date:
        clauses.append(f"{column} <= ?")
        params.append(end_date)
    return clauses, params


def client_summary(client_id: int, start_date: str | None = None, end_date: str | None = None):
    with get_conn() as conn:
        inv_where = ['client_id=?', "COALESCE(record_kind,'income_record')<>'estimate'"]
        inv_params = [client_id]
        add_clauses, add_params = between_clause('invoice_date', start_date, end_date)
        inv_where += add_clauses
        inv_params += add_params
        inv_sql = ' AND '.join(inv_where)
        gross = conn.execute(f'SELECT COALESCE(SUM(paid_amount),0) v FROM invoices WHERE {inv_sql}', tuple(inv_params)).fetchone()['v']
        count = conn.execute(f'SELECT COUNT(*) c FROM invoices WHERE {inv_sql}', tuple(inv_params)).fetchone()['c']

        gas_where = ['client_id=?']
        gas_params = [client_id]
        add_clauses, add_params = between_clause('week_start', start_date, end_date)
        gas_where += add_clauses
        gas_params += add_params
        gas_sql = ' AND '.join(gas_where)
        gas = conn.execute(f'SELECT COALESCE(SUM(amount),0) v FROM gas_entries WHERE {gas_sql}', tuple(gas_params)).fetchone()['v']

        mat_where = ['client_id=?']
        mat_params = [client_id]
        add_clauses, add_params = between_clause('material_date', start_date, end_date)
        mat_where += add_clauses
        mat_params += add_params
        mat_sql = ' AND '.join(mat_where)
        mat = conn.execute(f'SELECT COALESCE(SUM(amount),0) v FROM materials WHERE {mat_sql}', tuple(mat_params)).fetchone()['v']

        worker_where = ['w.client_id=?']
        worker_params = [client_id]
        add_clauses, add_params = between_clause('wp.payment_date', start_date, end_date)
        worker_where += add_clauses
        worker_params += add_params
        worker_sql = ' AND '.join(worker_where)
        worker = conn.execute(f'SELECT COALESCE(SUM(wp.amount),0) v FROM worker_payments wp JOIN workers w ON w.id=wp.worker_id WHERE {worker_sql}', tuple(worker_params)).fetchone()['v']

        mil_where = ['client_id=?']
        mil_params = [client_id]
        add_clauses, add_params = between_clause('trip_date', start_date, end_date)
        mil_where += add_clauses
        mil_params += add_params
        mil_sql = ' AND '.join(mil_where)
        row = conn.execute(f'SELECT COALESCE(SUM(miles),0) miles, COALESCE(SUM(deduction),0) deduction FROM mileage_entries WHERE {mil_sql}', tuple(mil_params)).fetchone()
        mileage_miles = row['miles']
        mileage_deduction = row['deduction']

    exp = gas + mat + worker
    operating_profit = max(gross - exp, 0)
    adjusted_profit = max(operating_profit - mileage_deduction, 0)
    return {
        'gross_income': round(gross, 2),
        'gas_total': round(gas, 2),
        'materials_total': round(mat, 2),
        'worker_total': round(worker, 2),
        'mileage_miles': round(mileage_miles, 2),
        'mileage_deduction': round(mileage_deduction, 2),
        'total_expenses': round(exp, 2),
        'operating_profit': round(operating_profit, 2),
        'adjusted_profit': round(adjusted_profit, 2),
        'taxable_profit': round(adjusted_profit, 2),
        'self_employment_tax_estimate': round(adjusted_profit * SELF_EMPLOYMENT_TAX_RATE, 2),
        'federal_plus_se_estimate': round(adjusted_profit * (SELF_EMPLOYMENT_TAX_RATE + FEDERAL_WITHHOLDING_RATE), 2),
        'invoice_count': count,
    }


def worker_year_totals(worker_id: int, year: int):
    with get_conn() as conn:
        payments = conn.execute('SELECT * FROM worker_payments WHERE worker_id=? AND substr(payment_date,1,4)=? ORDER BY payment_date, id', (worker_id, str(year))).fetchall()
        worker = conn.execute('SELECT * FROM workers WHERE id=?', (worker_id,)).fetchone()
    tax_rules = current_tax_rules(year)
    if not worker:
        return {'gross': 0.0, 'social_security_wages': 0.0, 'social_security_tax': 0.0, 'medicare_wages': 0.0, 'medicare_tax': 0.0, 'payroll': 0.0, 'federal': 0.0, 'net_check': 0.0, 'se': 0.0, 'additional_medicare_tax': 0.0}
    rollup = compute_worker_payment_rollup(worker, payments, tax_rules)
    totals = rollup['totals']
    se = money(totals['gross'] * SELF_EMPLOYMENT_TAX_RATE) if worker['worker_type'] != 'W-2' else 0.0
    return {
        'gross': totals['gross'],
        'social_security_wages': totals['social_security_wages'],
        'social_security_tax': totals['employee_social_security'],
        'medicare_wages': totals['medicare_wages'],
        'medicare_tax': money(totals['employee_medicare'] + totals['additional_medicare_tax']),
        'payroll': money(totals['employee_social_security'] + totals['employee_medicare'] + totals['additional_medicare_tax']),
        'federal': totals['federal_withholding'],
        'net_check': totals['net_check'],
        'se': se,
        'additional_medicare_tax': totals['additional_medicare_tax'],
    }


def payroll_tax_summary(client_id: int, year: int, quarter: int):
    q_start, q_end = quarter_date_range(year, quarter)
    checkpoint = date(year, quarter_months(quarter)[-1], 12)
    tax_rules = current_tax_rules(year)
    with get_conn() as conn:
        workers = conn.execute('SELECT * FROM workers WHERE client_id=? ORDER BY CASE WHEN status="active" THEN 0 ELSE 1 END, name', (client_id,)).fetchall()
        deposits = conn.execute('SELECT * FROM payroll_tax_deposits WHERE client_id=? AND tax_year=? AND tax_quarter=? ORDER BY deposit_date, id', (client_id, year, quarter)).fetchall()
    w2_workers = [w for w in workers if w['worker_type'] == 'W-2']
    included_details = []
    excluded_1099 = []
    line1_workers = set()
    monthly_liability = {m: 0.0 for m in quarter_months(quarter)}
    totals = {
        'line1': 0, 'line2_wages': 0.0, 'line3_federal': 0.0, 'line5a_wages': 0.0, 'line5a_tax': 0.0,
        'line5c_wages': 0.0, 'line5c_tax': 0.0, 'line5d_wages': 0.0, 'line5d_tax': 0.0, 'total_tax': 0.0,
        'deposits_total': 0.0, 'balance_due': 0.0, 'overpayment': 0.0
    }
    for worker in workers:
        with get_conn() as conn:
            all_year = conn.execute('SELECT * FROM worker_payments WHERE worker_id=? AND substr(payment_date,1,4)=? ORDER BY payment_date, id', (worker['id'], str(year))).fetchall()
        rollup = compute_worker_payment_rollup(worker, all_year, tax_rules)
        for detail in rollup['details']:
            pay_date = parse_date(detail['payment_date'])
            if not pay_date:
                continue
            if worker['worker_type'] != 'W-2':
                if q_start <= pay_date <= q_end:
                    excluded_1099.append(detail)
                continue
            if q_start <= pay_date <= q_end:
                included_details.append(detail)
                totals['line2_wages'] = money(totals['line2_wages'] + detail['gross'])
                totals['line3_federal'] = money(totals['line3_federal'] + detail['federal_withholding'])
                totals['line5a_wages'] = money(totals['line5a_wages'] + detail['social_security_wages'])
                totals['line5a_tax'] = money(totals['line5a_tax'] + detail['employee_social_security'] + detail['employer_social_security'])
                totals['line5c_wages'] = money(totals['line5c_wages'] + detail['medicare_wages'])
                totals['line5c_tax'] = money(totals['line5c_tax'] + detail['employee_medicare'] + detail['employer_medicare'])
                totals['line5d_wages'] = money(totals['line5d_wages'] + detail['additional_medicare_wages'])
                totals['line5d_tax'] = money(totals['line5d_tax'] + detail['additional_medicare_tax'])
                month = pay_date.month
                if month in monthly_liability:
                    monthly_liability[month] = money(monthly_liability[month] + detail['federal_withholding'] + detail['employee_social_security'] + detail['employer_social_security'] + detail['employee_medicare'] + detail['employer_medicare'] + detail['additional_medicare_tax'])
            # line 1 worker count based on pay period including the 12th of the quarter-ending month
            pay_frequency = (worker['payroll_frequency'] or 'weekly').lower()
            inferred_periods = inferred_withholding_periods(worker, detail, rollup['details'])
            if inferred_periods == 1 and q_start <= pay_date <= q_end:
                line1_workers.add(worker['id'])
            else:
                if pay_frequency == 'weekly':
                    period_start = pay_date.fromordinal(pay_date.toordinal() - 6)
                elif pay_frequency == 'biweekly':
                    period_start = pay_date.fromordinal(pay_date.toordinal() - 13)
                elif pay_frequency == 'semimonthly':
                    period_start = date(pay_date.year, pay_date.month, 1 if pay_date.day <= 15 else 16)
                else:
                    period_start = date(pay_date.year, pay_date.month, 1)
                if period_start <= checkpoint <= pay_date:
                    line1_workers.add(worker['id'])
    totals['line1'] = len(line1_workers)
    totals['total_tax'] = money(totals['line3_federal'] + totals['line5a_tax'] + totals['line5c_tax'] + totals['line5d_tax'])
    totals['deposits_total'] = money(sum(float(d['amount'] or 0) for d in deposits))
    diff = money(totals['total_tax'] - totals['deposits_total'])
    totals['balance_due'] = diff if diff > 0 else 0.0
    totals['overpayment'] = abs(diff) if diff < 0 else 0.0
    monthly_rows = []
    for month in quarter_months(quarter):
        month_deposits = money(sum(float(d['amount'] or 0) for d in deposits if int(d['tax_month']) == month))
        monthly_rows.append({'month': month, 'liability': monthly_liability[month], 'deposits': month_deposits, 'difference': money(monthly_liability[month] - month_deposits)})
    return {'totals': totals, 'details': included_details, 'excluded_1099': excluded_1099, 'deposits': deposits, 'monthly_rows': monthly_rows, 'tax_rules': tax_rules, 'year': year, 'quarter': quarter}


def cpa_dashboard_summary(user):
    ids = visible_client_ids(user)
    totals = {
        'business_count': len(ids),
        'gross_income': 0.0,
        'expenses': 0.0,
        'adjusted_profit': 0.0,
        'mileage_deduction': 0.0,
        'business_login_count': 0,
        'worker_portal_count': 0,
        'pending_worker_approvals': 0,
        'total_login_count': 0,
        'new_login_notifications': 0,
    }
    for cid in ids:
        s = client_summary(cid)
        totals['gross_income'] += s['gross_income']
        totals['expenses'] += s['total_expenses']
        totals['adjusted_profit'] += s['adjusted_profit']
        totals['mileage_deduction'] += s['mileage_deduction']
    for k in ('gross_income','expenses','adjusted_profit','mileage_deduction'):
        totals[k] = round(totals[k], 2)
    with get_conn() as conn:
        if ids:
            placeholders = ','.join('?' for _ in ids)
            business_logins = conn.execute(f"SELECT COUNT(*) v FROM users WHERE role='client' AND client_id IN ({placeholders})", tuple(ids)).fetchone()['v']
            worker_portals = conn.execute(f"SELECT COUNT(*) v FROM workers WHERE COALESCE(portal_access_enabled,0)=1 AND client_id IN ({placeholders})", tuple(ids)).fetchone()['v']
            pending_worker = conn.execute(f"SELECT COUNT(*) v FROM workers WHERE COALESCE(portal_access_enabled,0)=1 AND COALESCE(portal_approval_status,'approved')='pending' AND client_id IN ({placeholders})", tuple(ids)).fetchone()['v']
            new_login_notifications = conn.execute(f"SELECT COUNT(*) v FROM account_activity_log WHERE client_id IN ({placeholders})", tuple(ids)).fetchone()['v']
        else:
            business_logins = 0
            worker_portals = 0
            pending_worker = 0
            new_login_notifications = 0
    totals['business_login_count'] = int(business_logins or 0)
    totals['worker_portal_count'] = int(worker_portals or 0)
    totals['pending_worker_approvals'] = int(pending_worker or 0)
    totals['new_login_notifications'] = int(new_login_notifications or 0)
    totals['total_login_count'] = totals['business_login_count'] + totals['worker_portal_count'] + 1
    return totals




def latest_review_request(client_id: int):
    with get_conn() as conn:
        return conn.execute('SELECT prr.*, u.full_name submitted_by_name, ru.full_name reviewed_by_name FROM payroll_review_requests prr LEFT JOIN users u ON u.id=prr.submitted_by LEFT JOIN users ru ON ru.id=prr.reviewed_by WHERE prr.client_id=? ORDER BY prr.id DESC LIMIT 1', (client_id,)).fetchone()


def pending_review_alerts():
    with get_conn() as conn:
        return conn.execute('SELECT prr.*, c.business_name, u.full_name submitted_by_name FROM payroll_review_requests prr JOIN clients c ON c.id=prr.client_id LEFT JOIN users u ON u.id=prr.submitted_by WHERE prr.status="pending" ORDER BY prr.submitted_at DESC').fetchall()


def chat_messages(client_id: int):
    with get_conn() as conn:
        return conn.execute(
            """SELECT m.*, u.full_name sender_name, u.role sender_role,
                      ru.full_name recipient_name, ru.role recipient_role
               FROM internal_messages m
               JOIN users u ON u.id=m.sender_user_id
               LEFT JOIN users ru ON ru.id=m.recipient_user_id
               WHERE m.client_id=?
               ORDER BY m.id ASC""",
            (client_id,)
        ).fetchall()


def available_recipients(client_id: int, current_user_id: int):
    recipients = []
    for person in chat_participants(client_id):
        if person['id'] != current_user_id:
            recipients.append(person)
    return recipients


def default_recipient_id(client_id: int, user):
    recipients = available_recipients(client_id, user['id'])
    if not recipients:
        return None
    if user['role'] == 'admin':
        business_people = [p for p in recipients if p['role'] == 'client']
        if business_people:
            return business_people[0]['id']
    admin_people = [p for p in recipients if p['role'] == 'admin']
    if admin_people:
        return admin_people[0]['id']
    return recipients[0]['id']


def unread_message_count(client_id: int, user_id: int):
    with get_conn() as conn:
        row = conn.execute('SELECT COUNT(*) unread_count FROM internal_messages WHERE client_id=? AND recipient_user_id=? AND COALESCE(is_read,0)=0', (client_id, user_id)).fetchone()
    return int(row['unread_count'] or 0) if row else 0


def mark_messages_read(client_id: int, user_id: int):
    with get_conn() as conn:
        conn.execute('UPDATE internal_messages SET is_read=1 WHERE client_id=? AND recipient_user_id=? AND COALESCE(is_read,0)=0', (client_id, user_id))
        conn.commit()


def latest_incoming_message(client_id: int, user_id: int):
    with get_conn() as conn:
        return conn.execute(
            """SELECT m.*, u.full_name sender_name, u.role sender_role
               FROM internal_messages m
               JOIN users u ON u.id=m.sender_user_id
               WHERE m.client_id=? AND m.recipient_user_id=?
               ORDER BY m.id DESC LIMIT 1""",
            (client_id, user_id)
        ).fetchone()


def chat_recent_messages(client_id: int, limit: int = 18):
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM (
                    SELECT m.*, u.full_name sender_name, u.role sender_role,
                           ru.full_name recipient_name, ru.role recipient_role
                    FROM internal_messages m
                    JOIN users u ON u.id=m.sender_user_id
                    LEFT JOIN users ru ON ru.id=m.recipient_user_id
                    WHERE m.client_id=?
                    ORDER BY m.id DESC
                    LIMIT ?
                ) recent
                ORDER BY id ASC""",
            (client_id, limit)
        ).fetchall()
    return rows


def normalized_internal_chat_rows(client_id: int, user_id: int, limit: int = 18):
    rows = chat_recent_messages(client_id, limit=limit)
    normalized = []
    for row in rows:
        normalized.append({
            'is_mine': row['sender_user_id'] == user_id,
            'sender_name': row['sender_name'],
            'sender_role': 'Administrator' if row['sender_role'] == 'admin' else 'Business',
            'recipient_name': row['recipient_name'],
            'created_at': row['created_at'],
            'body': row['body'],
        })
    return normalized


def worker_manager_users(client_id: int):
    with get_conn() as conn:
        rows = conn.execute(
            '''SELECT id, full_name, role FROM users
               WHERE client_id=? OR role='admin'
               ORDER BY CASE WHEN role='client' THEN 0 ELSE 1 END, full_name''',
            (client_id,)
        ).fetchall()
    return rows


def primary_manager_user(client_id: int):
    managers = worker_manager_users(client_id)
    return managers[0] if managers else None


def worker_default_password_matches(worker, password: str) -> bool:
    typed = (password or '').strip()
    if not typed:
        return False
    candidates = set()
    ssn_digits = clean_digits(worker['ssn'])
    phone_digits = clean_digits(worker['phone'])
    if ssn_digits:
        candidates.add(ssn_digits[-4:])
    if phone_digits:
        candidates.add(phone_digits[-4:])
    return typed in candidates


def worker_time_summary_data(worker_id: int):
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)
    with get_conn() as conn:
        rows = conn.execute(
            'SELECT * FROM worker_time_entries WHERE worker_id=? ORDER BY entry_date DESC, id DESC',
            (worker_id,)
        ).fetchall()
        week_hours = conn.execute('SELECT COALESCE(SUM(hours),0) total FROM worker_time_entries WHERE worker_id=? AND entry_date>=?', (worker_id, week_start.isoformat())).fetchone()['total']
        month_hours = conn.execute('SELECT COALESCE(SUM(hours),0) total FROM worker_time_entries WHERE worker_id=? AND entry_date>=?', (worker_id, month_start.isoformat())).fetchone()['total']
        year_hours = conn.execute('SELECT COALESCE(SUM(hours),0) total FROM worker_time_entries WHERE worker_id=? AND entry_date>=?', (worker_id, year_start.isoformat())).fetchone()['total']
    return {
        'entries': rows,
        'week_hours': money(week_hours),
        'month_hours': money(month_hours),
        'year_hours': money(year_hours),
    }


def worker_payments_summary(worker_id: int):
    current_year = str(date.today().year)
    with get_conn() as conn:
        lifetime = conn.execute('SELECT COALESCE(SUM(amount),0) total FROM worker_payments WHERE worker_id=?', (worker_id,)).fetchone()['total']
        year_total = conn.execute("SELECT COALESCE(SUM(amount),0) total FROM worker_payments WHERE worker_id=? AND substr(payment_date,1,4)=?", (worker_id, current_year)).fetchone()['total']
        latest = conn.execute('SELECT * FROM worker_payments WHERE worker_id=? ORDER BY payment_date DESC, id DESC LIMIT 1', (worker_id,)).fetchone()
    return {
        'lifetime_total': money(lifetime),
        'year_total': money(year_total),
        'latest_payment': latest,
    }


def worker_payment_stub_context(worker, payment):
    if not worker or not payment:
        return None
    payment_year = int(str(payment['payment_date'] or date.today().year)[:4])
    with get_conn() as conn:
        year_payments = conn.execute(
            'SELECT * FROM worker_payments WHERE worker_id=? AND substr(payment_date,1,4)=? ORDER BY payment_date, id',
            (worker['id'], str(payment_year))
        ).fetchall()
    tax_rules = current_tax_rules(payment_year)
    rollup = compute_worker_payment_rollup(worker, year_payments, tax_rules)
    detail = next((row for row in rollup['details'] if row['id'] == payment['id']), None)
    if not detail:
        gross = money(payment['amount'] or 0)
        detail = {
            'id': payment['id'],
            'payment_date': payment['payment_date'],
            'gross': gross,
            'federal_withholding': 0.0,
            'employee_social_security': 0.0,
            'employee_medicare': 0.0,
            'additional_medicare_tax': 0.0,
            'net_check': gross,
            'social_security_wages': 0.0,
            'medicare_wages': 0.0,
        }
    running = {
        'gross': 0.0,
        'federal_withholding': 0.0,
        'employee_social_security': 0.0,
        'employee_medicare': 0.0,
        'additional_medicare_tax': 0.0,
        'net_check': 0.0,
    }
    for row in rollup['details']:
        for key in running:
            running[key] = money(running[key] + float(row.get(key, 0) or 0))
        if row['id'] == payment['id']:
            break
    employee_payroll_taxes = money(
        float(detail.get('employee_social_security', 0) or 0)
        + float(detail.get('employee_medicare', 0) or 0)
        + float(detail.get('additional_medicare_tax', 0) or 0)
    )
    return {
        'payment_year': payment_year,
        'detail': detail,
        'ytd': running,
        'employee_payroll_taxes': employee_payroll_taxes,
        'method_label': worker_payment_method_label_map().get(payment['payment_method'] or 'other', 'Other'),
        'status_label': worker_payment_status_label_map().get(payment['payment_status'] or 'paid', 'Paid'),
        'is_w2': (worker['worker_type'] or '').upper() == 'W-2',
    }


def default_worker_notice_sections():
    return [
        {
            'title': 'Attendance & Punctuality',
            'items': [
                'Arrive on time and confirm schedule changes with your manager before the shift.',
                'Notify your manager as early as possible if you will be late, absent, or unable to complete an assigned job.',
                'Review your assigned schedule regularly so job dates, addresses, and start times are not missed.'
            ]
        },
        {
            'title': 'Workplace Conduct & Respect',
            'items': [
                'Treat coworkers, customers, and managers respectfully at all times.',
                'Harassment, discrimination, threats, or abusive conduct are not allowed in the workplace or on job sites.',
                'Use the worker messenger only for work-related communication and job updates.'
            ]
        },
        {
            'title': 'Safety, Injuries & Timekeeping',
            'items': [
                'Follow safety instructions, ladder rules, equipment guidance, and required protective gear on every job.',
                'Report any injury, unsafe condition, or incident to your manager immediately so it can be documented properly.',
                'Review your time summary regularly and notify your manager promptly if hours, pay records, or job notes look incorrect.'
            ]
        },
    ]


def business_policy_notices(client_id: int):
    with get_conn() as conn:
        rows = conn.execute(
            '''SELECT wpn.*, u.full_name created_by_name
               FROM worker_policy_notices wpn
               LEFT JOIN users u ON u.id = wpn.created_by_user_id
               WHERE wpn.client_id=?
               ORDER BY wpn.updated_at DESC, wpn.id DESC''',
            (client_id,)
        ).fetchall()
    return rows



def normalize_worker_assignment_ids(raw_ids):
    normalized = []
    seen = set()
    for raw in raw_ids or []:
        try:
            worker_id = int(raw)
        except (TypeError, ValueError):
            continue
        if worker_id <= 0 or worker_id in seen:
            continue
        seen.add(worker_id)
        normalized.append(worker_id)
    return normalized


def assigned_worker_token(worker_ids):
    ids = normalize_worker_assignment_ids(worker_ids)
    return ',' + ','.join(str(wid) for wid in ids) + ',' if ids else ''


def worker_schedule_rows_for_client(client_id: int):
    with get_conn() as conn:
        prepare_ops_workspace(conn, client_id)
        rows = conn.execute(
            '''SELECT
                   j.id,
                   j.title AS job_name,
                   substr(COALESCE(j.scheduled_start, ''), 1, 10) AS schedule_date,
                   substr(COALESCE(j.scheduled_start, ''), 12, 5) AS start_time,
                   substr(COALESCE(j.scheduled_end, ''), 12, 5) AS end_time,
                   j.estimated_duration_minutes,
                   COALESCE(NULLIF(j.service_address, ''), sl.address_line1, '') AS job_address,
                   j.notes_summary AS scope_of_work,
                   COALESCE(NULLIF(j.dispatch_notes, ''), j.internal_notes, '') AS notes,
                   GROUP_CONCAT(w.name, ', ') AS assigned_worker_names
               FROM jobs j
               LEFT JOIN service_locations sl ON sl.id = j.service_location_id
               LEFT JOIN job_assignments ja
                 ON ja.job_id = j.id
                AND COALESCE(ja.status, 'assigned') <> 'removed'
               LEFT JOIN workers w ON w.id = ja.worker_id
               WHERE j.client_id=?
               GROUP BY j.id
               ORDER BY COALESCE(j.scheduled_start, ''), j.id DESC''',
            (client_id,)
        ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item['estimated_duration'] = ops_duration_label(item.get('estimated_duration_minutes') or 0)
        items.append(item)
    return items


def worker_schedule_rows_for_worker(worker_id: int, client_id: int):
    with get_conn() as conn:
        prepare_ops_workspace(conn, client_id)
        rows = conn.execute(
            '''SELECT
                   j.id,
                   j.title AS job_name,
                   substr(COALESCE(j.scheduled_start, ''), 1, 10) AS schedule_date,
                   substr(COALESCE(j.scheduled_start, ''), 12, 5) AS start_time,
                   substr(COALESCE(j.scheduled_end, ''), 12, 5) AS end_time,
                   j.estimated_duration_minutes,
                   COALESCE(NULLIF(j.service_address, ''), sl.address_line1, '') AS job_address,
                   j.notes_summary AS scope_of_work,
                   COALESCE(NULLIF(j.dispatch_notes, ''), j.internal_notes, '') AS notes
               FROM jobs j
               JOIN job_assignments ja
                 ON ja.job_id = j.id
                AND ja.worker_id = ?
                AND COALESCE(ja.status, 'assigned') <> 'removed'
               LEFT JOIN service_locations sl ON sl.id = j.service_location_id
               WHERE j.client_id=?
               ORDER BY COALESCE(j.scheduled_start, ''), j.id DESC''',
            (worker_id, client_id)
        ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item['estimated_duration'] = ops_duration_label(item.get('estimated_duration_minutes') or 0)
        items.append(item)
    return items


def worker_schedule_summary(rows):
    today_iso = date.today().isoformat()
    upcoming = [row for row in rows if (row['schedule_date'] or '') >= today_iso]
    next_item = upcoming[0] if upcoming else (rows[0] if rows else None)
    return {
        'total_items': len(rows),
        'upcoming_count': len(upcoming),
        'next_item': next_item,
    }


OPS_JOB_STATUSES = [
    ('draft', 'Draft'),
    ('unscheduled', 'Unscheduled'),
    ('scheduled', 'Scheduled'),
    ('assigned', 'Assigned'),
    ('in_progress', 'In Progress'),
    ('paused', 'Paused'),
    ('completed', 'Completed'),
    ('cancelled', 'Cancelled'),
    ('needs_follow_up', 'Needs Follow-Up'),
]
OPS_PROGRESS_STATUSES = [
    ('not_started', 'Not Started'),
    ('en_route', 'En Route'),
    ('on_site', 'On Site'),
    ('paused', 'Paused'),
    ('completed', 'Completed'),
    ('requires_revisit', 'Requires Revisit'),
]
OPS_PRIORITIES = [
    ('low', 'Low'),
    ('normal', 'Normal'),
    ('high', 'High'),
    ('urgent', 'Urgent'),
]
OPS_AVAILABILITY_STATUSES = [
    ('available', 'Available'),
    ('limited', 'Limited'),
    ('unavailable', 'Unavailable'),
    ('time_off', 'Time Off'),
]


def ops_job_status_options():
    return OPS_JOB_STATUSES


def ops_progress_status_options():
    return OPS_PROGRESS_STATUSES


def ops_priority_options():
    return OPS_PRIORITIES


def ops_availability_status_options():
    return OPS_AVAILABILITY_STATUSES


def ops_label(value: str, fallback: str = 'Unknown') -> str:
    raw = (value or '').strip()
    return raw.replace('_', ' ').replace('-', ' ').title() if raw else fallback


def normalize_ops_choice(value: str, allowed_options, default: str) -> str:
    cleaned = (value or '').strip().lower()
    allowed = {key for key, _ in allowed_options}
    return cleaned if cleaned in allowed else default


def normalize_ops_job_status(value: str, *, default: str = 'unscheduled') -> str:
    return normalize_ops_choice(value, OPS_JOB_STATUSES, default)


def normalize_ops_progress_status(value: str, *, default: str = 'not_started') -> str:
    return normalize_ops_choice(value, OPS_PROGRESS_STATUSES, default)


def normalize_ops_priority(value: str, *, default: str = 'normal') -> str:
    return normalize_ops_choice(value, OPS_PRIORITIES, default)


def normalize_ops_availability_status(value: str, *, default: str = 'available') -> str:
    return normalize_ops_choice(value, OPS_AVAILABILITY_STATUSES, default)


def ops_clean_csv(value: str) -> str:
    seen = []
    for piece in re.split(r'[,;]', value or ''):
        cleaned = piece.strip()
        if cleaned and cleaned.lower() not in {item.lower() for item in seen}:
            seen.append(cleaned)
    return ', '.join(seen)


def ops_schedule_timestamp(date_value: str, time_value: str = '') -> str:
    date_clean = (date_value or '').strip()
    if not date_clean:
        return ''
    time_clean = (time_value or '').strip()
    return f'{date_clean}T{time_clean}' if time_clean else date_clean


def ops_schedule_date(iso_value: str) -> str:
    return (iso_value or '')[:10]


def ops_schedule_time(iso_value: str) -> str:
    return (iso_value or '')[11:16] if 'T' in (iso_value or '') else ''


def ops_parse_datetime(iso_value: str):
    raw = (iso_value or '').strip()
    if not raw:
        return None
    try:
        if 'T' in raw:
            return datetime.fromisoformat(raw)
        return datetime.fromisoformat(f'{raw}T00:00')
    except ValueError:
        return None


def ops_duration_label(minutes: int | None) -> str:
    total = int(minutes or 0)
    if total <= 0:
        return ''
    hours, mins = divmod(total, 60)
    if hours and mins:
        return f'{hours}h {mins}m'
    if hours:
        return f'{hours}h'
    return f'{mins}m'


def ops_duration_minutes(start_iso: str, end_iso: str, fallback: int = 0) -> int:
    start_dt = ops_parse_datetime(start_iso)
    end_dt = ops_parse_datetime(end_iso)
    if start_dt and end_dt and end_dt > start_dt:
        return int((end_dt - start_dt).total_seconds() // 60)
    return max(int(fallback or 0), 0)


def ops_schedule_end(date_value: str, start_time: str, end_time: str, duration_minutes: int) -> str:
    if (date_value or '').strip() and (end_time or '').strip():
        return ops_schedule_timestamp(date_value, end_time)
    start_iso = ops_schedule_timestamp(date_value, start_time)
    start_dt = ops_parse_datetime(start_iso)
    if start_dt and int(duration_minutes or 0) > 0:
        return (start_dt + timedelta(minutes=int(duration_minutes))).strftime('%Y-%m-%dT%H:%M')
    return ''


def ops_range_overlap(start_a: str, end_a: str, start_b: str, end_b: str) -> bool:
    a1 = ops_parse_datetime(start_a)
    a2 = ops_parse_datetime(end_a) or a1
    b1 = ops_parse_datetime(start_b)
    b2 = ops_parse_datetime(end_b) or b1
    if not all([a1, a2, b1, b2]):
        return False
    return a1 < b2 and b1 < a2


def ops_log_activity(conn: sqlite3.Connection, *, client_id: int, job_id: int, actor_type: str, actor_id=None, event_type: str = 'updated', event_text: str = ''):
    conn.execute(
        '''INSERT INTO job_activity_log (client_id, job_id, actor_type, actor_id, event_type, event_text)
           VALUES (?,?,?,?,?,?)''',
        (client_id, job_id, (actor_type or 'system').strip()[:50], actor_id, (event_type or 'updated').strip()[:50], (event_text or '').strip()[:400]),
    )


def ops_ensure_reference_data(conn: sqlite3.Connection, client_id: int):
    if not client_id:
        return
    for item in OPS_DEFAULT_SERVICE_TYPES:
        existing = conn.execute(
            'SELECT id FROM service_types WHERE client_id=? AND lower(name)=lower(?)',
            (client_id, item['name']),
        ).fetchone()
        if not existing:
            conn.execute(
                '''INSERT INTO service_types (
                       client_id, name, description, default_duration_minutes,
                       default_priority, default_crew_size, color_token, is_active, updated_at
                   ) VALUES (?,?,?,?,?,?,?,?,?)''',
                (
                    client_id,
                    item['name'],
                    item['description'],
                    item['default_duration_minutes'],
                    item['default_priority'],
                    item['default_crew_size'],
                    item['color_token'],
                    1,
                    now_iso(),
                ),
            )
    type_map = {
        row['name']: row['id']
        for row in conn.execute('SELECT id, name FROM service_types WHERE client_id=?', (client_id,)).fetchall()
    }
    default_templates = [
        ('Standard Service Visit', 'Cleaning', 'Standard service visit', 180, 'normal', 2, 'Arrival check, equipment check, completion confirmation'),
        ('Crew Dispatch', 'Landscaping', 'Crew dispatch job', 240, 'high', 3, 'Route check, arrival confirmation, completion handoff'),
        ('Follow-Up Visit', 'Custom', 'Follow-up visit', 90, 'normal', 1, 'Issue review, corrective work, customer confirmation'),
    ]
    for name, service_name, default_title, duration_minutes, priority, crew_size, checklist_text in default_templates:
        exists = conn.execute(
            'SELECT id FROM job_templates WHERE client_id=? AND lower(name)=lower(?)',
            (client_id, name),
        ).fetchone()
        if not exists:
            conn.execute(
                '''INSERT INTO job_templates (
                       client_id, service_type_id, name, default_title, default_duration_minutes,
                       default_priority, default_crew_size, checklist_text, is_active, updated_at
                   ) VALUES (?,?,?,?,?,?,?,?,?,?)''',
                (
                    client_id,
                    type_map.get(service_name),
                    name,
                    default_title,
                    duration_minutes,
                    priority,
                    crew_size,
                    checklist_text,
                    1,
                    now_iso(),
                ),
            )


def ops_find_or_create_location(
    conn: sqlite3.Connection,
    *,
    client_id: int,
    customer_contact_id=None,
    location_name: str = '',
    address_line1: str = '',
    city: str = '',
    state: str = '',
    postal_code: str = '',
    access_notes: str = '',
    gate_code: str = '',
    parking_notes: str = '',
    location_notes: str = '',
):
    location_name = (location_name or '').strip()
    address_line1 = (address_line1 or '').strip()
    city = (city or '').strip()
    state = (state or '').strip()
    postal_code = (postal_code or '').strip()
    if not any([location_name, address_line1, city, state, postal_code]):
        return None
    row = conn.execute(
        '''SELECT id
           FROM service_locations
           WHERE client_id=?
             AND lower(COALESCE(address_line1, ''))=lower(?)
             AND lower(COALESCE(city, ''))=lower(?)
             AND lower(COALESCE(state, ''))=lower(?)
             AND lower(COALESCE(postal_code, ''))=lower(?)
           LIMIT 1''',
        (client_id, address_line1, city, state, postal_code),
    ).fetchone()
    if row:
        conn.execute(
            '''UPDATE service_locations
               SET location_name=CASE WHEN COALESCE(location_name, '')='' THEN ? ELSE location_name END,
                   customer_contact_id=COALESCE(customer_contact_id, ?),
                   access_notes=CASE WHEN COALESCE(access_notes, '')='' THEN ? ELSE access_notes END,
                   gate_code=CASE WHEN COALESCE(gate_code, '')='' THEN ? ELSE gate_code END,
                   parking_notes=CASE WHEN COALESCE(parking_notes, '')='' THEN ? ELSE parking_notes END,
                   location_notes=CASE WHEN COALESCE(location_notes, '')='' THEN ? ELSE location_notes END,
                   updated_at=?
               WHERE id=?''',
            (location_name, customer_contact_id, access_notes, gate_code, parking_notes, location_notes, now_iso(), row['id']),
        )
        return row['id']
    conn.execute(
        '''INSERT INTO service_locations (
               client_id, customer_contact_id, location_name, address_line1, city, state, postal_code,
               access_notes, gate_code, parking_notes, location_notes, updated_at
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
        (
            client_id,
            customer_contact_id,
            location_name,
            address_line1,
            city,
            state,
            postal_code,
            access_notes,
            gate_code,
            parking_notes,
            location_notes,
            now_iso(),
        ),
    )
    return conn.execute('SELECT last_insert_rowid()').fetchone()[0]


def ops_sync_job_assignments(conn: sqlite3.Connection, *, client_id: int, job_id: int, worker_ids, actor_user_id=None):
    normalized_ids = normalize_worker_assignment_ids(worker_ids)
    existing_rows = conn.execute(
        '''SELECT ja.worker_id, w.name
           FROM job_assignments ja
           JOIN workers w ON w.id = ja.worker_id
           WHERE ja.job_id=?''',
        (job_id,),
    ).fetchall()
    existing_ids = [int(row['worker_id']) for row in existing_rows]
    worker_name_map = {
        row['id']: row['name']
        for row in conn.execute('SELECT id, name FROM workers WHERE client_id=?', (client_id,)).fetchall()
    }
    for worker_id in existing_ids:
        if worker_id not in normalized_ids:
            conn.execute('DELETE FROM job_assignments WHERE job_id=? AND worker_id=?', (job_id, worker_id))
            ops_log_activity(
                conn,
                client_id=client_id,
                job_id=job_id,
                actor_type='user',
                actor_id=actor_user_id,
                event_type='assignment_removed',
                event_text=f"Removed {worker_name_map.get(worker_id, 'worker')} from the crew.",
            )
    for index, worker_id in enumerate(normalized_ids):
        if worker_id in existing_ids:
            conn.execute(
                '''UPDATE job_assignments
                   SET status='assigned', sort_order=?, assigned_by_user_id=COALESCE(assigned_by_user_id, ?)
                   WHERE job_id=? AND worker_id=?''',
                (index, actor_user_id, job_id, worker_id),
            )
            continue
        conn.execute(
            '''INSERT INTO job_assignments (job_id, worker_id, assignment_role, assigned_by_user_id, status, sort_order)
               VALUES (?,?,?,?,?,?)''',
            (job_id, worker_id, 'crew_member', actor_user_id, 'assigned', index),
        )
        ops_log_activity(
            conn,
            client_id=client_id,
            job_id=job_id,
            actor_type='user',
            actor_id=actor_user_id,
            event_type='assignment_added',
            event_text=f"Assigned {worker_name_map.get(worker_id, 'worker')} to the job.",
        )


def migrate_legacy_schedule_to_jobs(conn: sqlite3.Connection):
    try:
        legacy_rows = conn.execute(
            '''SELECT *
               FROM work_schedule_entries
               ORDER BY schedule_date, id'''
        ).fetchall()
    except sqlite3.Error:
        return
    for row in legacy_rows:
        existing = conn.execute(
            'SELECT id FROM jobs WHERE legacy_schedule_entry_id=?',
            (row['id'],),
        ).fetchone()
        if existing:
            continue
        client_id = int(row['client_id'] or 0)
        if not client_id:
            continue
        ops_ensure_reference_data(conn, client_id)
        location_id = ops_find_or_create_location(
            conn,
            client_id=client_id,
            location_name=row['job_name'],
            address_line1=row['job_address'] or '',
            location_notes=row['notes'] or '',
        )
        service_type = conn.execute(
            'SELECT id, name FROM service_types WHERE client_id=? ORDER BY CASE WHEN lower(name)=? THEN 0 ELSE 1 END, name LIMIT 1',
            (client_id, 'custom'),
        ).fetchone()
        scheduled_start = ops_schedule_timestamp(row['schedule_date'] or '', row['start_time'] or '')
        scheduled_end = ops_schedule_timestamp(row['schedule_date'] or '', row['end_time'] or '')
        estimated_minutes = ops_duration_minutes(scheduled_start, scheduled_end, 0)
        status = 'assigned' if (row['assigned_worker_ids'] or '').strip() else 'scheduled'
        conn.execute(
            '''INSERT INTO jobs (
                   client_id, legacy_schedule_entry_id, service_location_id, service_type_id, created_by_user_id, updated_by_user_id,
                   title, service_type_name, status, field_progress_status, service_address, scheduled_start, scheduled_end,
                   estimated_duration_minutes, notes_summary, internal_notes, updated_at
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (
                client_id,
                row['id'],
                location_id,
                service_type['id'] if service_type else None,
                row['created_by_user_id'],
                row['created_by_user_id'],
                (row['job_name'] or 'Imported Schedule Entry').strip(),
                service_type['name'] if service_type else 'Custom',
                status,
                'not_started',
                (row['job_address'] or '').strip(),
                scheduled_start,
                scheduled_end,
                estimated_minutes,
                (row['scope_of_work'] or '').strip(),
                (row['notes'] or '').strip(),
                now_iso(),
            ),
        )
        job_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        worker_ids = normalize_worker_assignment_ids((row['assigned_worker_ids'] or '').split(','))
        ops_sync_job_assignments(conn, client_id=client_id, job_id=job_id, worker_ids=worker_ids, actor_user_id=row['created_by_user_id'])
        ops_log_activity(
            conn,
            client_id=client_id,
            job_id=job_id,
            actor_type='system',
            actor_id=row['created_by_user_id'],
            event_type='legacy_import',
            event_text='Imported a legacy work schedule entry into Operational LedgerFlow.',
        )


def prepare_ops_workspace(conn: sqlite3.Connection, client_id: int):
    ops_ensure_reference_data(conn, client_id)
    migrate_legacy_schedule_to_jobs(conn)
    conn.commit()


def ops_service_types(conn: sqlite3.Connection, client_id: int):
    prepare_ops_workspace(conn, client_id)
    return conn.execute(
        'SELECT * FROM service_types WHERE client_id=? AND COALESCE(is_active, 1)=1 ORDER BY name',
        (client_id,),
    ).fetchall()


def ops_job_templates(conn: sqlite3.Connection, client_id: int):
    prepare_ops_workspace(conn, client_id)
    return conn.execute(
        '''SELECT jt.*, st.name AS service_type_name
           FROM job_templates jt
           LEFT JOIN service_types st ON st.id = jt.service_type_id
           WHERE jt.client_id=?
           ORDER BY COALESCE(jt.is_active, 1) DESC, jt.name''',
        (client_id,),
    ).fetchall()


def ops_jobs_query(
    conn: sqlite3.Connection,
    *,
    client_id: int,
    job_id: int | None = None,
    status: str = '',
    worker_id: int | None = None,
    service_type_id: int | None = None,
    search: str = '',
    date_from: str = '',
    date_to: str = '',
):
    clauses = ['j.client_id=?']
    params = [client_id]
    if job_id:
        clauses.append('j.id=?')
        params.append(job_id)
    if status:
        clauses.append('j.status=?')
        params.append(normalize_ops_job_status(status))
    if worker_id:
        clauses.append('EXISTS (SELECT 1 FROM job_assignments ja2 WHERE ja2.job_id=j.id AND ja2.worker_id=? AND COALESCE(ja2.status, "assigned") <> "removed")')
        params.append(worker_id)
    if service_type_id:
        clauses.append('j.service_type_id=?')
        params.append(service_type_id)
    if search:
        clauses.append('(lower(j.title) LIKE ? OR lower(COALESCE(j.customer_name, "")) LIKE ? OR lower(COALESCE(j.service_address, "")) LIKE ? OR lower(COALESCE(j.tags, "")) LIKE ?)')
        term = f"%{search.strip().lower()}%"
        params.extend([term, term, term, term])
    if date_from:
        clauses.append('substr(COALESCE(j.scheduled_start, ""), 1, 10) >= ?')
        params.append(date_from)
    if date_to:
        clauses.append('substr(COALESCE(j.scheduled_start, ""), 1, 10) <= ?')
        params.append(date_to)
    where_sql = ' AND '.join(clauses)
    return conn.execute(
        f'''SELECT
                j.*,
                COALESCE(st.name, j.service_type_name, 'Custom') AS service_type_label,
                COALESCE(sl.location_name, '') AS location_name,
                COALESCE(sl.access_notes, '') AS access_notes,
                COALESCE(sl.gate_code, '') AS gate_code,
                COALESCE(sl.parking_notes, '') AS parking_notes,
                GROUP_CONCAT(w.name, ', ') AS assigned_worker_names,
                GROUP_CONCAT(CAST(w.id AS TEXT), ',') AS assigned_worker_ids_csv,
                COUNT(ja.id) AS assigned_count
            FROM jobs j
            LEFT JOIN service_types st ON st.id = j.service_type_id
            LEFT JOIN service_locations sl ON sl.id = j.service_location_id
            LEFT JOIN job_assignments ja
              ON ja.job_id = j.id
             AND COALESCE(ja.status, 'assigned') <> 'removed'
            LEFT JOIN workers w ON w.id = ja.worker_id
            WHERE {where_sql}
            GROUP BY j.id
            ORDER BY
                CASE j.status
                    WHEN 'in_progress' THEN 0
                    WHEN 'needs_follow_up' THEN 1
                    WHEN 'assigned' THEN 2
                    WHEN 'scheduled' THEN 3
                    WHEN 'unscheduled' THEN 4
                    WHEN 'draft' THEN 5
                    WHEN 'paused' THEN 6
                    WHEN 'completed' THEN 7
                    WHEN 'cancelled' THEN 8
                    ELSE 9
                END,
                COALESCE(j.scheduled_start, ''),
                j.id DESC''',
        tuple(params),
    ).fetchall()


def ops_job_notes_for_job(conn: sqlite3.Connection, job_id: int):
    return conn.execute(
        '''SELECT jn.*, u.full_name
           FROM job_notes jn
           LEFT JOIN users u ON u.id = jn.created_by_user_id
           WHERE jn.job_id=?
           ORDER BY jn.created_at DESC, jn.id DESC''',
        (job_id,),
    ).fetchall()


def ops_job_activity_for_job(conn: sqlite3.Connection, job_id: int, limit: int = 40):
    return conn.execute(
        '''SELECT jal.*
           FROM job_activity_log jal
           WHERE jal.job_id=?
           ORDER BY jal.created_at DESC, jal.id DESC
           LIMIT ?''',
        (job_id, limit),
    ).fetchall()


def ops_finance_summary(conn: sqlite3.Connection, client_id: int):
    monday = (date.today() - timedelta(days=date.today().weekday())).isoformat()
    invoice_row = conn.execute(
        '''SELECT
               COUNT(*) AS total_invoices,
               COUNT(CASE WHEN COALESCE(record_kind, '')='customer_invoice' AND COALESCE(invoice_status, 'draft') NOT IN ('paid', 'cancelled') THEN 1 END) AS outstanding_invoice_count,
               COALESCE(SUM(CASE WHEN COALESCE(record_kind, 'income_record') <> 'estimate' AND COALESCE(invoice_date, '') >= ? THEN paid_amount ELSE 0 END), 0) AS revenue_week
           FROM invoices
           WHERE client_id=?''',
        (monday, client_id),
    ).fetchone()
    billing_row = conn.execute(
        '''SELECT
               COUNT(*) AS pending_billing_alerts,
               COALESCE(SUM(amount_due), 0) AS pending_billing_amount
           FROM business_payment_items
           WHERE client_id=?
             AND COALESCE(status, 'pending') IN ('pending', 'processing')''',
        (client_id,),
    ).fetchone()
    return {
        'outstanding_invoice_count': int(invoice_row['outstanding_invoice_count'] or 0) if invoice_row else 0,
        'revenue_week': float(invoice_row['revenue_week'] or 0) if invoice_row else 0.0,
        'pending_billing_alerts': int(billing_row['pending_billing_alerts'] or 0) if billing_row else 0,
        'pending_billing_amount': float(billing_row['pending_billing_amount'] or 0) if billing_row else 0.0,
    }


def ops_worker_rows(conn: sqlite3.Connection, client_id: int):
    today_iso = date.today().isoformat()
    return conn.execute(
        '''SELECT
               w.*,
               COALESCE(NULLIF(w.worker_role, ''), NULLIF(w.role_classification, ''), 'Crew Member') AS ops_role,
               COUNT(DISTINCT CASE WHEN COALESCE(j.status, '') NOT IN ('completed', 'cancelled') AND substr(COALESCE(j.scheduled_start, ''), 1, 10) >= ? THEN j.id END) AS upcoming_assignments,
               COUNT(DISTINCT CASE WHEN COALESCE(j.status, '')='in_progress' THEN j.id END) AS active_assignments,
               MAX(substr(COALESCE(j.scheduled_start, ''), 1, 10)) AS next_assignment_date
           FROM workers w
           LEFT JOIN job_assignments ja
             ON ja.worker_id = w.id
            AND COALESCE(ja.status, 'assigned') <> 'removed'
           LEFT JOIN jobs j ON j.id = ja.job_id
           WHERE w.client_id=?
           GROUP BY w.id
           ORDER BY CASE WHEN COALESCE(w.status, 'active')='active' THEN 0 ELSE 1 END, w.name''',
        (today_iso, client_id),
    ).fetchall()


def ops_availability_rows(conn: sqlite3.Connection, client_id: int, start_date: str = '', end_date: str = ''):
    clauses = ['wa.client_id=?']
    params = [client_id]
    if start_date:
        clauses.append('wa.available_date>=?')
        params.append(start_date)
    if end_date:
        clauses.append('wa.available_date<=?')
        params.append(end_date)
    return conn.execute(
        f'''SELECT wa.*, w.name AS worker_name
            FROM worker_availability wa
            JOIN workers w ON w.id = wa.worker_id
            WHERE {' AND '.join(clauses)}
            ORDER BY wa.available_date, wa.start_time, w.name''',
        tuple(params),
    ).fetchall()


def ops_conflicts(conn: sqlite3.Connection, client_id: int):
    jobs = ops_jobs_query(conn, client_id=client_id)
    assignments = conn.execute(
        '''SELECT ja.job_id, ja.worker_id, w.name, COALESCE(w.status, 'active') AS worker_status
           FROM job_assignments ja
           JOIN workers w ON w.id = ja.worker_id
           JOIN jobs j ON j.id = ja.job_id
           WHERE j.client_id=?
             AND COALESCE(ja.status, 'assigned') <> 'removed'
             AND COALESCE(j.status, '') NOT IN ('completed', 'cancelled')''',
        (client_id,),
    ).fetchall()
    jobs_by_id = {row['id']: row for row in jobs}
    conflicts = []
    by_worker = {}
    for row in assignments:
        job = jobs_by_id.get(row['job_id'])
        if not job:
            continue
        if (row['worker_status'] or 'active') != 'active':
            conflicts.append({
                'kind': 'inactive_worker',
                'worker_name': row['name'],
                'job_title': job['title'],
                'detail': f"{row['name']} is inactive but still assigned to {job['title']}.",
            })
        by_worker.setdefault(row['worker_id'], []).append((row['name'], job))
    for worker_jobs in by_worker.values():
        ordered = sorted(worker_jobs, key=lambda pair: (pair[1]['scheduled_start'] or '', pair[1]['id']))
        for idx in range(len(ordered) - 1):
            worker_name, first_job = ordered[idx]
            _, second_job = ordered[idx + 1]
            if ops_range_overlap(first_job['scheduled_start'], first_job['scheduled_end'], second_job['scheduled_start'], second_job['scheduled_end']):
                conflicts.append({
                    'kind': 'overlap',
                    'worker_name': worker_name,
                    'job_title': first_job['title'],
                    'detail': f"{worker_name} is double-booked on {first_job['title']} and {second_job['title']}.",
                })
    availability_rows = ops_availability_rows(conn, client_id, date.today().isoformat(), (date.today() + timedelta(days=30)).isoformat())
    availability_index = {}
    for row in availability_rows:
        availability_index.setdefault((row['worker_id'], row['available_date']), []).append(row)
    for row in assignments:
        job = jobs_by_id.get(row['job_id'])
        if not job:
            continue
        job_date = ops_schedule_date(job['scheduled_start'])
        for availability in availability_index.get((row['worker_id'], job_date), []):
            availability_status = normalize_ops_availability_status(availability['availability_status'])
            if availability_status == 'available':
                continue
            slot_start = ops_schedule_timestamp(job_date, availability['start_time'])
            slot_end = ops_schedule_timestamp(job_date, availability['end_time']) if availability['end_time'] else job['scheduled_end']
            if availability_status == 'time_off' or ops_range_overlap(job['scheduled_start'], job['scheduled_end'], slot_start, slot_end):
                conflicts.append({
                    'kind': 'availability',
                    'worker_name': row['name'],
                    'job_title': job['title'],
                    'detail': f"{row['name']} is marked {ops_label(availability_status)} during {job['title']}.",
                })
                break
    time_off_rows = conn.execute(
        '''SELECT tor.*, w.name AS worker_name
           FROM worker_time_off_requests tor
           JOIN workers w ON w.id = tor.worker_id
           WHERE w.client_id=?
             AND COALESCE(tor.status, 'pending') IN ('pending', 'approved')
           ORDER BY tor.start_date, tor.end_date''',
        (client_id,),
    ).fetchall()
    for row in time_off_rows:
        for worker_name, job in by_worker.get(row['worker_id'], []):
            job_date = ops_schedule_date(job['scheduled_start'])
            if row['start_date'] <= job_date <= (row['end_date'] or row['start_date']):
                conflicts.append({
                    'kind': 'time_off',
                    'worker_name': worker_name,
                    'job_title': job['title'],
                    'detail': f"{worker_name} has a time-off request overlapping {job['title']}.",
                })
                break
    return conflicts


def ops_int(value, default: int | None = None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def ops_recent_activity(conn: sqlite3.Connection, client_id: int, limit: int = 16, search: str = ''):
    clauses = ['jal.client_id=?']
    params = [client_id]
    if search:
        clauses.append('(lower(jal.event_text) LIKE ? OR lower(COALESCE(j.title, "")) LIKE ?)')
        term = f"%{search.strip().lower()}%"
        params.extend([term, term])
    params.append(limit)
    return conn.execute(
        f'''SELECT jal.*, j.title AS job_title
            FROM job_activity_log jal
            LEFT JOIN jobs j ON j.id = jal.job_id
            WHERE {' AND '.join(clauses)}
            ORDER BY jal.created_at DESC, jal.id DESC
            LIMIT ?''',
        tuple(params),
    ).fetchall()


def ops_dashboard_summary(conn: sqlite3.Connection, client_id: int):
    prepare_ops_workspace(conn, client_id)
    jobs = [dict(row) for row in ops_jobs_query(conn, client_id=client_id)]
    today_iso = date.today().isoformat()
    now_value = datetime.now()
    today_jobs = [job for job in jobs if ops_schedule_date(job['scheduled_start']) == today_iso and job['status'] not in {'draft', 'cancelled'}]
    unassigned_jobs = [job for job in jobs if int(job['assigned_count'] or 0) == 0 and job['status'] not in {'completed', 'cancelled'}]
    overdue_jobs = []
    for job in jobs:
        if job['status'] in {'completed', 'cancelled', 'draft'}:
            continue
        start_dt = ops_parse_datetime(job['scheduled_start'])
        if start_dt and start_dt < now_value:
            overdue_jobs.append(job)
    active_jobs = [job for job in jobs if job['status'] == 'in_progress']
    completed_today = [job for job in jobs if job['status'] == 'completed' and ops_schedule_date(job['completed_at'] or job['scheduled_start']) == today_iso]
    crews = {((job.get('assigned_worker_names') or '').strip()) for job in active_jobs if (job.get('assigned_worker_names') or '').strip()}
    completion_ratio = int(round((len(completed_today) / max(len(today_jobs), 1)) * 100)) if today_jobs else 0
    return {
        'jobs': jobs,
        'today_jobs': today_jobs,
        'unassigned_jobs': unassigned_jobs,
        'overdue_jobs': overdue_jobs,
        'active_jobs': active_jobs,
        'active_crews': crews,
        'completion_ratio': completion_ratio,
        'completed_today': completed_today,
        'conflicts': ops_conflicts(conn, client_id),
        'recent_activity': ops_recent_activity(conn, client_id),
        'finance_summary': ops_finance_summary(conn, client_id),
    }


def ops_save_job(conn: sqlite3.Connection, *, client_id: int, actor_user_id: int, form, existing=None) -> int:
    title = (form.get('title', '') or '').strip()
    if not title:
        raise ValueError('Job title is required.')
    service_type_id = ops_int(form.get('service_type_id'))
    service_type = conn.execute(
        'SELECT * FROM service_types WHERE id=? AND client_id=?',
        (service_type_id, client_id),
    ).fetchone() if service_type_id else None
    scheduled_date = (form.get('scheduled_date', '') or '').strip()
    start_time = (form.get('start_time', '') or '').strip()
    end_time = (form.get('end_time', '') or '').strip()
    estimated_duration_minutes = max(ops_int(form.get('estimated_duration_minutes'), 0) or 0, 0)
    scheduled_start = ops_schedule_timestamp(scheduled_date, start_time)
    scheduled_end = ops_schedule_end(scheduled_date, start_time, end_time, estimated_duration_minutes)
    estimated_duration_minutes = ops_duration_minutes(scheduled_start, scheduled_end, estimated_duration_minutes)
    priority = normalize_ops_priority(form.get('priority'), default=(service_type['default_priority'] if service_type else 'normal'))
    status = normalize_ops_job_status(form.get('status'), default='unscheduled')
    progress_status = normalize_ops_progress_status(form.get('field_progress_status'), default='not_started')
    assigned_worker_ids = normalize_worker_assignment_ids(form.getlist('assigned_worker_ids'))
    if scheduled_start and status in {'draft', 'unscheduled'}:
        status = 'scheduled'
    if assigned_worker_ids and status in {'scheduled', 'draft', 'unscheduled'}:
        status = 'assigned'
    if status == 'in_progress' and progress_status == 'not_started':
        progress_status = 'on_site'
    if status == 'paused':
        progress_status = 'paused'
    if status == 'completed':
        progress_status = 'completed'
    requires_revisit = 1 if form.get('requires_revisit') else 0
    if requires_revisit:
        status = 'needs_follow_up'
        progress_status = 'requires_revisit'
    issue_flag = 1 if form.get('issue_flag') else 0
    location_id = ops_find_or_create_location(
        conn,
        client_id=client_id,
        customer_contact_id=ops_int(form.get('customer_contact_id')),
        location_name=(form.get('location_name', '') or '').strip(),
        address_line1=(form.get('service_address', '') or '').strip(),
        city=(form.get('city', '') or '').strip(),
        state=(form.get('state', '') or '').strip(),
        postal_code=(form.get('postal_code', '') or '').strip(),
        access_notes=(form.get('access_notes', '') or '').strip(),
        gate_code=(form.get('gate_code', '') or '').strip(),
        parking_notes=(form.get('parking_notes', '') or '').strip(),
        location_notes=(form.get('location_notes', '') or '').strip(),
    ) or (existing['service_location_id'] if existing else None)
    payload = (
        ops_int(form.get('customer_contact_id')),
        location_id,
        service_type_id,
        ops_int(form.get('template_id')),
        title,
        (form.get('customer_name', '') or '').strip(),
        (form.get('customer_reference', '') or '').strip(),
        service_type['name'] if service_type else (existing['service_type_name'] if existing else 'Custom'),
        priority,
        status,
        progress_status,
        ops_clean_csv(form.get('tags', '')),
        (form.get('service_address', '') or '').strip(),
        (form.get('city', '') or '').strip(),
        (form.get('state', '') or '').strip(),
        (form.get('postal_code', '') or '').strip(),
        scheduled_start,
        scheduled_end,
        estimated_duration_minutes,
        (form.get('notes_summary', '') or '').strip(),
        (form.get('internal_notes', '') or '').strip(),
        (form.get('dispatch_notes', '') or '').strip(),
        (form.get('completion_notes', '') or '').strip(),
        (form.get('recurrence_rule', '') or '').strip(),
        1 if (form.get('recurrence_rule', '') or '').strip() else 0,
        (form.get('cancellation_reason', '') or '').strip(),
        issue_flag,
        requires_revisit,
        now_iso() if status == 'completed' else '',
        now_iso() if progress_status != 'not_started' else '',
        now_iso(),
        actor_user_id,
    )
    if existing:
        conn.execute(
            '''UPDATE jobs
               SET customer_contact_id=?, service_location_id=?, service_type_id=?, template_id=?, title=?, customer_name=?, customer_reference=?,
                   service_type_name=?, priority=?, status=?, field_progress_status=?, tags=?, service_address=?, city=?, state=?, postal_code=?,
                   scheduled_start=?, scheduled_end=?, estimated_duration_minutes=?, notes_summary=?, internal_notes=?, dispatch_notes=?,
                   completion_notes=?, recurrence_rule=?, is_recurring=?, cancellation_reason=?, issue_flag=?, requires_revisit=?, completed_at=?,
                   last_progress_at=?, updated_at=?, updated_by_user_id=?
               WHERE id=?''',
            payload + (existing['id'],),
        )
        job_id = existing['id']
        if existing['status'] != status:
            ops_log_activity(
                conn,
                client_id=client_id,
                job_id=job_id,
                actor_type='user',
                actor_id=actor_user_id,
                event_type='status_changed',
                event_text=f"Changed status from {ops_label(existing['status'])} to {ops_label(status)}.",
            )
        else:
            ops_log_activity(
                conn,
                client_id=client_id,
                job_id=job_id,
                actor_type='user',
                actor_id=actor_user_id,
                event_type='updated',
                event_text='Updated job details.',
            )
    else:
        conn.execute(
            '''INSERT INTO jobs (
                   client_id, customer_contact_id, service_location_id, service_type_id, template_id, created_by_user_id, updated_by_user_id,
                   title, customer_name, customer_reference, service_type_name, priority, status, field_progress_status, tags,
                   service_address, city, state, postal_code, scheduled_start, scheduled_end, estimated_duration_minutes,
                   notes_summary, internal_notes, dispatch_notes, completion_notes, recurrence_rule, is_recurring, cancellation_reason,
                   issue_flag, requires_revisit, completed_at, last_progress_at, updated_at
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (
                client_id,
                payload[0],
                payload[1],
                payload[2],
                payload[3],
                actor_user_id,
                actor_user_id,
                payload[4],
                payload[5],
                payload[6],
                payload[7],
                payload[8],
                payload[9],
                payload[10],
                payload[11],
                payload[12],
                payload[13],
                payload[14],
                payload[15],
                payload[16],
                payload[17],
                payload[18],
                payload[19],
                payload[20],
                payload[21],
                payload[22],
                payload[23],
                payload[24],
                payload[25],
                payload[26],
                payload[27],
                payload[28],
                payload[29],
                payload[30],
            ),
        )
        job_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        ops_log_activity(
            conn,
            client_id=client_id,
            job_id=job_id,
            actor_type='user',
            actor_id=actor_user_id,
            event_type='created',
            event_text='Created the job record.',
        )
    ops_sync_job_assignments(conn, client_id=client_id, job_id=job_id, worker_ids=assigned_worker_ids, actor_user_id=actor_user_id)
    return job_id


def ops_duplicate_job(conn: sqlite3.Connection, *, client_id: int, job_id: int, actor_user_id: int) -> int | None:
    source = conn.execute('SELECT * FROM jobs WHERE id=? AND client_id=?', (job_id, client_id)).fetchone()
    if not source:
        return None
    conn.execute(
        '''INSERT INTO jobs (
               client_id, customer_contact_id, service_location_id, service_type_id, template_id, created_by_user_id, updated_by_user_id,
               title, customer_name, customer_reference, service_type_name, priority, status, field_progress_status, tags,
               service_address, city, state, postal_code, scheduled_start, scheduled_end, estimated_duration_minutes,
               notes_summary, internal_notes, dispatch_notes, completion_notes, recurrence_rule, is_recurring, cancellation_reason,
               issue_flag, requires_revisit, completed_at, last_progress_at, updated_at
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (
            client_id,
            source['customer_contact_id'],
            source['service_location_id'],
            source['service_type_id'],
            source['template_id'],
            actor_user_id,
            actor_user_id,
            f"{source['title']} (Copy)",
            source['customer_name'],
            source['customer_reference'],
            source['service_type_name'],
            source['priority'],
            'unscheduled',
            'not_started',
            source['tags'],
            source['service_address'],
            source['city'],
            source['state'],
            source['postal_code'],
            '',
            '',
            source['estimated_duration_minutes'],
            source['notes_summary'],
            source['internal_notes'],
            source['dispatch_notes'],
            '',
            source['recurrence_rule'],
            source['is_recurring'],
            '',
            source['issue_flag'],
            0,
            '',
            '',
            now_iso(),
        ),
    )
    new_job_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    assignment_ids = [
        row['worker_id']
        for row in conn.execute('SELECT worker_id FROM job_assignments WHERE job_id=? ORDER BY sort_order, id', (job_id,)).fetchall()
    ]
    ops_sync_job_assignments(conn, client_id=client_id, job_id=new_job_id, worker_ids=assignment_ids, actor_user_id=actor_user_id)
    ops_log_activity(
        conn,
        client_id=client_id,
        job_id=new_job_id,
        actor_type='user',
        actor_id=actor_user_id,
        event_type='duplicated',
        event_text=f"Duplicated from job #{job_id}.",
    )
    return new_job_id


def ops_save_worker_profile(conn: sqlite3.Connection, *, client_id: int, actor_user_id: int, form, existing=None) -> int:
    name = (form.get('name', '') or '').strip()
    if not name:
        raise ValueError('Worker name is required.')
    worker_role = (form.get('worker_role', '') or '').strip()
    status = (form.get('status', '') or '').strip().lower() or 'active'
    if status not in {'active', 'inactive', 'terminated'}:
        status = 'active'
    payload = (
        name,
        worker_role,
        worker_role,
        (form.get('phone', '') or '').strip(),
        (form.get('email', '') or '').strip(),
        normalize_language(form.get('preferred_language') or 'en'),
        (form.get('crew_label', '') or '').strip(),
        ops_clean_csv(form.get('skill_tags', '')),
        (form.get('availability_baseline', '') or '').strip(),
        status,
        now_iso(),
        actor_user_id,
    )
    if existing:
        conn.execute(
            '''UPDATE workers
               SET name=?, worker_role=?, role_classification=?, phone=?, email=?, preferred_language=?, crew_label=?, skill_tags=?,
                   availability_baseline=?, status=?, updated_at=?, updated_by_user_id=?
               WHERE id=?''',
            payload + (existing['id'],),
        )
        worker_id = existing['id']
        log_worker_profile_history(conn, worker_id=worker_id, client_id=client_id, action='updated', changed_by_user_id=actor_user_id)
    else:
        conn.execute(
            '''INSERT INTO workers (
                   client_id, name, worker_type, phone, email, preferred_language, role_classification, worker_role,
                   crew_label, skill_tags, availability_baseline, status, created_by_user_id, updated_at, updated_by_user_id
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (
                client_id,
                name,
                '1099',
                payload[3],
                payload[4],
                payload[5],
                worker_role,
                worker_role,
                payload[6],
                payload[7],
                payload[8],
                status,
                actor_user_id,
                now_iso(),
                actor_user_id,
            ),
        )
        worker_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        conn.execute('INSERT OR IGNORE INTO w4_answers (worker_id, signed_date) VALUES (?,?)', (worker_id, date.today().isoformat()))
        log_worker_profile_history(conn, worker_id=worker_id, client_id=client_id, action='created', changed_by_user_id=actor_user_id)
    return worker_id


def worker_time_off_rows(worker_id: int):
    with get_conn() as conn:
        return conn.execute(
            'SELECT * FROM worker_time_off_requests WHERE worker_id=? ORDER BY created_at DESC, id DESC',
            (worker_id,)
        ).fetchall()


def worker_message_rows(worker_id: int):
    with get_conn() as conn:
        return conn.execute(
            '''SELECT wm.*, u.full_name manager_name
               FROM worker_messages wm
               LEFT JOIN users u ON u.id = wm.sender_user_id
               WHERE wm.worker_id=?
               ORDER BY wm.id ASC''',
            (worker_id,)
        ).fetchall()


def normalized_worker_message_rows(worker, manager, limit: int = 18):
    rows = worker_message_rows(worker['id'])
    manager_name = manager['full_name'] if manager else (worker['business_contact_name'] or f"{worker['business_name']} Manager")
    normalized = []
    for row in rows[-limit:]:
        is_mine = row['sender_kind'] == 'worker'
        normalized.append({
            'is_mine': is_mine,
            'sender_name': worker['name'] if is_mine else (row['manager_name'] or manager_name),
            'sender_role': 'Worker' if is_mine else 'Manager',
            'recipient_name': '',
            'created_at': row['created_at'],
            'body': row['body'],
        })
    return normalized


def worker_unread_message_count(worker_id: int):
    with get_conn() as conn:
        row = conn.execute('SELECT COUNT(*) unread_count FROM worker_messages WHERE worker_id=? AND sender_kind="manager" AND COALESCE(is_read_worker,0)=0', (worker_id,)).fetchone()
    return int(row['unread_count'] or 0) if row else 0


def mark_worker_messages_read(worker_id: int):
    with get_conn() as conn:
        conn.execute('UPDATE worker_messages SET is_read_worker=1 WHERE worker_id=? AND sender_kind="manager" AND COALESCE(is_read_worker,0)=0', (worker_id,))
        conn.commit()


def selected_client_id(user, source='get'):
    cid = request.form.get('client_id', type=int) if source == 'post' and user['role'] == 'admin' else request.args.get('client_id', type=int) if source == 'get' and user['role'] == 'admin' else user['client_id']
    if user['role'] == 'admin' and not cid:
        ids = visible_client_ids(user)
        cid = ids[0] if ids else None
    if not cid or not allowed_client(user, cid):
        abort(403)
    return cid


def user_presence_meta(last_seen_at: str):
    if not last_seen_at:
        return {'status': 'offline', 'label': 'Offline', 'detail': 'No recent activity'}
    try:
        last_seen = datetime.fromisoformat(last_seen_at)
    except ValueError:
        return {'status': 'offline', 'label': 'Offline', 'detail': 'No recent activity'}
    now = datetime.now()
    diff = now - last_seen
    if diff <= timedelta(minutes=3):
        return {'status': 'online', 'label': 'Online', 'detail': 'Active now'}
    if diff <= timedelta(minutes=15):
        mins = max(1, int(diff.total_seconds() // 60))
        return {'status': 'away', 'label': 'Away', 'detail': f'Active {mins}m ago'}
    if diff <= timedelta(hours=24):
        hours = max(1, int(diff.total_seconds() // 3600))
        return {'status': 'offline', 'label': 'Offline', 'detail': f'Active {hours}h ago'}
    return {'status': 'offline', 'label': 'Offline', 'detail': f'Last active {last_seen.strftime("%b %d, %Y %I:%M %p")}' }


def chat_participants(client_id: int):
    with get_conn() as conn:
        rows = conn.execute('SELECT u.id, u.full_name, u.role, u.last_seen_at FROM users u WHERE u.role="admin" OR u.client_id=? ORDER BY CASE WHEN u.role="admin" THEN 0 ELSE 1 END, u.full_name', (client_id,)).fetchall()
    participants = []
    for row in rows:
        meta = user_presence_meta(row['last_seen_at'])
        participants.append({
            'id': row['id'],
            'full_name': row['full_name'],
            'role': row['role'],
            'presence': meta['status'],
            'presence_label': meta['label'],
            'presence_detail': meta['detail'],
        })
    return participants


def current_request_path() -> str:
    full = request.full_path or request.path or '/'
    return full[:-1] if full.endswith('?') else full


def shell_messenger_client_id(user, active_client, clients):
    if not user or user['role'] not in {'admin', 'client'}:
        return None
    if user['role'] == 'client':
        return user['client_id']
    explicit = request.values.get('client_id', type=int) or request.values.get('messenger_client_id', type=int)
    if explicit and allowed_client(user, explicit):
        return explicit
    if active_client:
        return active_client['id']
    ids = [row['id'] for row in clients or []]
    return ids[0] if ids else None


def internal_shell_messenger_context(user, active_client, clients):
    client_id = shell_messenger_client_id(user, active_client, clients)
    if not client_id:
        return {'enabled': False}
    with get_conn() as conn:
        client = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
    if not client:
        return {'enabled': False}
    recipients = available_recipients(client_id, user['id'])
    latest = latest_incoming_message(client_id, user['id'])
    return {
        'enabled': True,
        'kind': 'internal',
        'client_id': client_id,
        'client_name': client['business_name'],
        'title': client['business_name'],
        'subtitle': 'Open a live thread without leaving the page you are working on.',
        'messages': normalized_internal_chat_rows(client_id, user['id']),
        'unread_count': unread_message_count(client_id, user['id']),
        'recipients': recipients,
        'selected_recipient_id': default_recipient_id(client_id, user),
        'latest_incoming': {
            'sender_name': latest['sender_name'],
            'created_at': latest['created_at'],
            'body': latest['body'],
        } if latest else None,
    }


def worker_shell_messenger_context(worker):
    manager = primary_manager_user(worker['client_id'])
    manager_name = manager['full_name'] if manager else (worker['business_contact_name'] or f"{worker['business_name']} Manager")
    return {
        'enabled': True,
        'kind': 'worker',
        'title': manager_name,
        'subtitle': 'Your manager thread stays available while you move through the worker portal.',
        'messages': normalized_worker_message_rows(worker, manager),
        'unread_count': worker_unread_message_count(worker['id']),
        'recipients': [],
        'selected_recipient_id': None,
        'latest_incoming': None,
    }


def assistant_first_name(name: str) -> str:
    raw = (name or '').strip()
    if not raw:
        return 'there'
    return raw.split()[0]


def assistant_category_for_key(key: str) -> str:
    mapping = {
        'overview': 'Workspace',
        'welcome_center': 'Onboarding',
        'billing': 'Billing',
        'billing_setup': 'Billing',
        'income_records': 'Records',
        'team_members': 'Team',
        'team_payouts': 'Payroll',
        'calendar': 'Planning',
        'benefits': 'Compliance',
        'reports': 'Reporting',
        'admin_workspace': 'Administrator',
        'businesses': 'Records',
        'business_users': 'Access',
        'email_settings': 'Email',
        'invite_delivery': 'Email',
        'admin_calendar': 'Planning',
        'admin_tasks': 'Operations',
        'archive_rejoin': 'Retention',
        'time_summary': 'Work',
        'pay_stubs': 'Payroll',
        'schedule': 'Work',
        'time_off': 'Work',
        'notices': 'Communication',
        'manager_messages': 'Communication',
    }
    return mapping.get(key, 'Guidance')


def assistant_default_steps(key: str, title: str) -> list[str]:
    category = assistant_category_for_key(key)
    if category == 'Billing':
        return [
            'Open the billing surface and review what is currently due, active, or missing.',
            'Confirm the payment method or subscription posture before making changes.',
            'Use the primary billing action there so the status updates cleanly in LedgerFlow.',
        ]
    if category in {'Team', 'Payroll', 'Work'}:
        return [
            f'Open {title} to review the current people or pay information first.',
            'Check the active records or pending items before creating a new change.',
            'Use the main action on that page so the portal and reporting stay aligned.',
        ]
    if category in {'Email', 'Access', 'Retention'}:
        return [
            f'Open {title} and start with the latest visible status or delivery result.',
            'Review whether the issue is invite, access, or recovery related before acting.',
            'Use the guided action there so outreach, login flow, and history stay preserved.',
        ]
    if category in {'Planning', 'Compliance'}:
        return [
            f'Open {title} and review the current deadlines, rules, or reference items.',
            'Use the official links or structured reminders on that page before changing records.',
            'Return to the working page after you confirm the timing or obligation you need.',
        ]
    if category in {'Reporting', 'Records'}:
        return [
            f'Open {title} and review the current records or totals first.',
            'Use the structured entry or reporting tools instead of loose notes or memory.',
            'Finish by checking that the result now shows up in the business workflow correctly.',
        ]
    return [
        f'Open {title} from the guided link below.',
        'Review the key summary or action area on that page first.',
        'Use the primary action there to move the workflow forward in LedgerFlow.',
    ]


def assistant_default_why(key: str, title: str) -> str:
    category = assistant_category_for_key(key)
    if category == 'Billing':
        return 'Billing clarity protects trust, access, and payment confidence across the workspace.'
    if category in {'Team', 'Payroll', 'Work'}:
        return 'People and payroll actions create downstream effects, so the cleanest first move matters.'
    if category in {'Email', 'Access', 'Retention'}:
        return 'Invite, access, and comeback flows are business-critical because they affect activation and recovery.'
    if category in {'Planning', 'Compliance'}:
        return 'Timing and compliance mistakes are expensive, so this page is meant to reduce surprises before they happen.'
    if category in {'Reporting', 'Records'}:
        return 'Structured records are what make tax prep, reporting, and business visibility feel professional later.'
    return f'{title} matters because it controls an important part of the LedgerFlow workflow.'


def assistant_default_outcome(key: str, title: str) -> str:
    category = assistant_category_for_key(key)
    if category == 'Billing':
        return 'A clean billing posture with the right payment method, subscription state, and fee visibility.'
    if category in {'Team', 'Payroll', 'Work'}:
        return 'A cleaner people workflow where pay, schedules, and portal visibility stay aligned.'
    if category in {'Email', 'Access', 'Retention'}:
        return 'A clear outreach or access result with history preserved and the next action obvious.'
    if category in {'Planning', 'Compliance'}:
        return 'A calmer forward plan with better deadline control and fewer compliance blind spots.'
    if category in {'Reporting', 'Records'}:
        return 'A tax-ready, report-ready record structure that is easier to trust later.'
    return f'A cleaner result inside {title} with less friction in the rest of the system.'


def assistant_default_caution(key: str, title: str) -> str:
    category = assistant_category_for_key(key)
    if category == 'Billing':
        return 'Do not change billing posture before you confirm the active method, fee state, and subscription status.'
    if category in {'Team', 'Payroll', 'Work'}:
        return 'Do not make people or payroll changes casually. Review the current record first so the portal and pay history stay coherent.'
    if category in {'Email', 'Access', 'Retention'}:
        return 'Do not assume delivery or access is correct until you check the latest status, preview, or recovery record.'
    if category in {'Planning', 'Compliance'}:
        return 'Do not rely on memory when a date, notice, or compliance rule is involved.'
    if category in {'Reporting', 'Records'}:
        return 'Do not store important business information as loose notes if LedgerFlow already has a structured record for it.'
    return f'Do not skip the structured workflow inside {title} if you want the system to stay clean.'


def assistant_topic(
    key: str,
    title: str,
    summary: str,
    response: str,
    keywords=None,
    link_label: str = '',
    link_url: str = '',
    *,
    steps=None,
    best_for: str = '',
    category: str = '',
    why: str = '',
    outcome: str = '',
    caution: str = '',
) -> dict:
    return {
        'key': key,
        'title': title,
        'summary': summary,
        'response': response,
        'keywords': list(keywords or []),
        'link_label': link_label,
        'link_url': link_url,
        'category': category or assistant_category_for_key(key),
        'best_for': best_for or summary,
        'steps': list(steps or assistant_default_steps(key, title)),
        'why': why or assistant_default_why(key, title),
        'outcome': outcome or assistant_default_outcome(key, title),
        'caution': caution or assistant_default_caution(key, title),
    }


def assistant_capabilities(role: str) -> list[str]:
    if role == 'worker':
        return ['Page-aware', 'Voice-ready', 'Payroll guidance']
    if role == 'admin':
        return ['Page-aware', 'Workflow guidance', 'Operations-ready']
    return ['Page-aware', 'Voice-ready', 'Business guidance']


def assistant_page_brief(page_label: str, topics) -> str:
    if not topics:
        return f'You are on {page_label}. Ask anything about this part of LedgerFlow and I will guide you to the right next step.'
    primary = topics[0]
    secondary = topics[1] if len(topics) > 1 else None
    if secondary:
        return f'{page_label} is best used by starting with {primary["title"].lower()}, then moving into {secondary["title"].lower()} when you are ready for the next step.'
    return f'{page_label} is best used by starting with {primary["title"].lower()} first so the rest of the workflow stays clean.'


def assistant_starter_questions(role: str, topics) -> list[str]:
    prompts = ['Explain this page', 'What should I do next?', 'Show me the safest workflow']
    if topics:
        prompts.append(f'How do I use {topics[0]["title"]}?')
    if role == 'admin':
        prompts.append('Where do invites or onboarding get managed?')
    elif role == 'worker':
        prompts.append('How do I check pay and schedule?')
    else:
        prompts.append('How do I keep this business tax-ready?')
    return prompts[:5]


def assistant_match_topic(query: str, topics) -> dict | None:
    text = (query or '').strip().lower()
    if not text:
        return topics[0] if topics else None
    best = None
    best_score = 0
    for topic in topics or []:
        score = 0
        title = (topic.get('title') or '').lower()
        if text in title or title in text:
            score += 4
        for keyword in topic.get('keywords', []):
            if str(keyword).lower() in text:
                score += 3
        for part in title.split():
            if part and part in text:
                score += 1
        if score > best_score:
            best = topic
            best_score = score
    return best or (topics[0] if topics else None)


def assistant_runtime_snapshot(user, worker, active_client, current_mode: str) -> dict:
    endpoint = request.endpoint or ''
    page_label = assistant_page_label(endpoint)
    if worker:
        topics = ordered_assistant_topics(worker_assistant_topics(), endpoint)
        return {
            'role': 'team_member',
            'person_name': worker['name'],
            'business_name': worker['business_name'],
            'page_label': page_label,
            'context_label': f'Currently on {page_label} for {worker["business_name"]}.',
            'topics': topics,
        }
    if not user:
        return {'role': 'guest', 'person_name': '', 'business_name': '', 'page_label': page_label, 'context_label': f'Currently on {page_label}.', 'topics': []}
    if user['role'] == 'admin':
        topics = ordered_assistant_topics(admin_assistant_topics(active_client, current_mode), endpoint)
        context_label = (
            f'Currently on {page_label} for {active_client["business_name"]}.'
            if active_client and current_mode == 'business'
            else f'Currently on {page_label}.'
        )
        business_name = active_client['business_name'] if active_client else ''
        role = 'administrator'
    else:
        topics = ordered_assistant_topics(business_assistant_topics(active_client), endpoint)
        context_label = f'Currently on {page_label} for {active_client["business_name"]}.'
        business_name = active_client['business_name'] if active_client else ''
        role = 'business_user'
    return {
        'role': role,
        'person_name': user['full_name'],
        'business_name': business_name,
        'page_label': page_label,
        'context_label': context_label,
        'topics': topics,
    }


def default_ai_assistant_system_prompt() -> str:
    return (
        'You are LedgerFlow Guide AI inside a premium finance and operations platform for small businesses. '
        'Act like a calm, high-trust product concierge. '
        'Give decisive, software-specific guidance that helps the user move to the right LedgerFlow page or action. '
        'Do not mention being a language model. Do not invent features or data not present in the provided context. '
        'When possible, explain the safest next step, why it matters, what outcome to expect, and one caution to avoid.'
    )


def build_ai_assistant_request(question: str, snapshot: dict, matched_topic: dict | None) -> tuple[str, str]:
    person_name = assistant_first_name(snapshot.get('person_name', ''))
    role = snapshot.get('role', 'user')
    business_name = snapshot.get('business_name', '')
    page_label = snapshot.get('page_label', 'this page')
    context_label = snapshot.get('context_label', '')
    topics = snapshot.get('topics', [])[:5]
    topic_lines = []
    for topic in topics:
        topic_lines.append(
            f"- {topic['title']} ({topic['category']}): {topic['response']} Best for: {topic['best_for']} Link: {topic['link_label'] or 'Open related page'}"
        )
    matched_lines = []
    if matched_topic:
        matched_lines = [
            f"Matched local workflow topic: {matched_topic['title']}",
            f"Matched topic reason: {matched_topic['why']}",
            f"Matched topic outcome: {matched_topic['outcome']}",
            f"Matched topic caution: {matched_topic['caution']}",
        ]

    instructions = default_ai_assistant_system_prompt()
    payload = (
        f"User first name: {person_name}\n"
        f"Role: {role}\n"
        f"Business: {business_name}\n"
        f"Current page: {page_label}\n"
        f"Context: {context_label}\n"
        f"Question: {question}\n\n"
        "Relevant LedgerFlow topics:\n"
        + "\n".join(topic_lines)
        + "\n\n"
        + "\n".join(matched_lines)
        + "\n\n"
        "Return JSON with these exact fields: "
        "title, message, best_for, why, outcome, caution, steps. "
        "The steps field must be an array with 2 to 4 concise LedgerFlow-specific steps."
    )
    return instructions, payload


def call_openai_assistant(question: str, snapshot: dict, matched_topic: dict | None) -> dict:
    config = ai_assistant_config()
    if config.get('api_key_unreadable'):
        raise RuntimeError('Saved AI API key must be entered again once after the security-key update.')
    if not config.get('configured'):
        raise RuntimeError('AI Guide is not configured yet.')
    instructions, prompt = build_ai_assistant_request(question, snapshot, matched_topic)
    full_instructions = instructions
    if config.get('system_prompt'):
        full_instructions += ' ' + config['system_prompt']
    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'title': {'type': 'string'},
            'message': {'type': 'string'},
            'best_for': {'type': 'string'},
            'why': {'type': 'string'},
            'outcome': {'type': 'string'},
            'caution': {'type': 'string'},
            'steps': {
                'type': 'array',
                'minItems': 2,
                'maxItems': 4,
                'items': {'type': 'string'},
            },
        },
        'required': ['title', 'message', 'best_for', 'why', 'outcome', 'caution', 'steps'],
    }
    body = json.dumps({
        'model': config['model'],
        'instructions': full_instructions,
        'input': prompt,
        'text': {
            'format': {
                'type': 'json_schema',
                'name': 'ledgerflow_guide_reply',
                'schema': schema,
                'strict': True,
            }
        },
    }).encode('utf-8')
    req = urlrequest.Request(
        'https://api.openai.com/v1/responses',
        data=body,
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {config["api_key"]}',
        },
        method='POST',
    )
    try:
        with urlrequest.urlopen(req, timeout=35) as response:
            raw = json.loads(response.read().decode('utf-8'))
    except urlerror.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='ignore')
        raise RuntimeError(detail[:300] or f'AI request failed with status {exc.code}.')
    except Exception as exc:
        raise RuntimeError(str(exc))

    output_items = raw.get('output', [])
    text_parts = []
    for item in output_items:
        if item.get('type') != 'message':
            continue
        for content in item.get('content', []):
            if content.get('type') == 'output_text':
                text_parts.append(content.get('text', ''))
    raw_text = ''.join(text_parts).strip()
    if not raw_text:
        raise RuntimeError('AI response did not contain usable text.')
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        raise RuntimeError('AI response was not valid structured output.')
    return {
        'title': (parsed.get('title') or matched_topic['title'] if matched_topic else 'LedgerFlow Guide AI').strip(),
        'message': (parsed.get('message') or '').strip(),
        'best_for': (parsed.get('best_for') or '').strip(),
        'why': (parsed.get('why') or '').strip(),
        'outcome': (parsed.get('outcome') or '').strip(),
        'caution': (parsed.get('caution') or '').strip(),
        'steps': [str(step).strip() for step in (parsed.get('steps') or []) if str(step).strip()],
    }


def assistant_page_label(endpoint: str) -> str:
    labels = {
        'cpa_dashboard': 'Administrator Dashboard',
        'clients': 'Businesses',
        'client_users': 'Business Users',
        'email_settings': 'Email Settings',
        'admin_calendar': 'Administrator Calendar',
        'admin_tasks': 'Admin Tasks',
        'dashboard': 'Business Overview',
        'welcome_center': 'Welcome Center',
        'summary': 'Summary',
        'invoices': 'Income Records',
        'workers': 'Team Members',
        'worker_payments': 'Team Member Payouts',
        'business_payments_page': 'Billing',
        'business_calendar': 'Business Calendar',
        'work_schedule': 'Work Schedule',
        'reports': 'Reports',
        'benefits_obligations': 'Benefits & Obligations',
        'worker_time_summary': 'Time Summary',
        'worker_pay_stubs': 'Pay Stubs',
        'worker_pay_stub_detail': 'Pay Stub Detail',
        'worker_schedule': 'Schedule',
        'worker_time_off': 'Time Off Request',
        'worker_notices': 'Policies & Notices',
        'worker_messages': 'Manager Messenger',
    }
    return labels.get(endpoint or '', 'this page')


def assistant_priority_keys(endpoint: str) -> list[str]:
    return {
        'cpa_dashboard': ['admin_workspace', 'billing_setup', 'businesses'],
        'clients': ['businesses', 'archive_rejoin', 'admin_workspace'],
        'client_users': ['business_users', 'prospect_pipeline', 'email_settings'],
        'email_settings': ['email_settings', 'invite_delivery', 'admin_workspace'],
        'admin_calendar': ['admin_calendar', 'invite_delivery', 'businesses'],
        'admin_tasks': ['admin_tasks', 'business_users', 'businesses'],
        'dashboard': ['overview', 'billing', 'income_records'],
        'welcome_center': ['welcome_center', 'overview', 'billing'],
        'summary': ['overview', 'reports', 'income_records'],
        'invoices': ['income_records', 'billing', 'reports'],
        'workers': ['team_members', 'team_payouts', 'calendar'],
        'worker_payments': ['team_payouts', 'team_members', 'billing'],
        'business_payments_page': ['billing', 'income_records', 'calendar'],
        'business_calendar': ['calendar', 'billing', 'benefits'],
        'work_schedule': ['calendar', 'team_members', 'team_payouts'],
        'reports': ['reports', 'income_records', 'billing'],
        'benefits_obligations': ['benefits', 'team_members', 'billing'],
        'worker_time_summary': ['time_summary', 'pay_stubs', 'manager_messages'],
        'worker_pay_stubs': ['pay_stubs', 'time_summary', 'manager_messages'],
        'worker_pay_stub_detail': ['pay_stubs', 'time_summary', 'manager_messages'],
        'worker_schedule': ['schedule', 'time_off', 'manager_messages'],
        'worker_time_off': ['time_off', 'schedule', 'manager_messages'],
        'worker_notices': ['notices', 'manager_messages', 'pay_stubs'],
        'worker_messages': ['manager_messages', 'time_summary', 'pay_stubs'],
    }.get(endpoint or '', [])


def ordered_assistant_topics(topics, endpoint: str):
    priorities = assistant_priority_keys(endpoint)
    order = {key: index for index, key in enumerate(priorities)}
    return sorted(
        topics,
        key=lambda topic: (order.get(topic['key'], 99), topic['title']),
    )


def business_assistant_topics(active_client) -> list[dict]:
    client_id = active_client['id']
    business_name = active_client['business_name']
    return [
        assistant_topic(
            'overview',
            'Understand this workspace',
            'Get oriented fast so the dashboard feels useful instead of crowded.',
            f'The Overview page is your command center for {business_name}. Start there for billing health, current reminders, workspace status, and the fastest path into the rest of LedgerFlow.',
            ['overview', 'dashboard', 'home', 'where do i start', 'start'],
            'Open Overview',
            url_for('dashboard', client_id=client_id),
        ),
        assistant_topic(
            'billing',
            'Manage subscription and fees',
            'Review subscription status, payment methods, and administrator fees.',
            'Open Billing to review your subscription, payment methods on file, one-time administrator fees, and the current payment posture of the business. This is the main place to settle anything tied to access or billing trust.',
            ['billing', 'subscription', 'payment', 'fee', 'invoice payment', 'card', 'bank'],
            'Open Billing',
            url_for('business_payments_page', client_id=client_id),
        ),
        assistant_topic(
            'income_records',
            'Record income the tax-ready way',
            'Track income inside LedgerFlow without making it look like a client-facing invoice.',
            'Income Records are for internal tax preparation and business bookkeeping. Use them to capture service income, product sales, sales-tax portions, and supporting details in a structure that is cleaner for year-end reporting.',
            ['income', 'invoice', 'sales', 'service income', 'record income', 'tax prep'],
            'Open Income Records',
            url_for('invoices', client_id=client_id),
        ),
        assistant_topic(
            'team_members',
            'Set up team members correctly',
            'Add, manage, and organize people who work inside the business.',
            'Use Team Members to store worker records, portal access, notices, and payroll-related details. This is also where you keep the people side of the business clean before payouts and pay stubs happen.',
            ['team', 'employee', 'worker', 'member', 'people', 'staff'],
            'Open Team Members',
            url_for('workers', client_id=client_id),
        ),
        assistant_topic(
            'team_payouts',
            'Handle payouts and pay stubs',
            'Review payroll-side activity, team payouts, and worker payment records.',
            'Team Member Payouts is where you document and manage payment activity for the team. It connects directly to the portal and pay stub experience, so changes here affect what the team sees later.',
            ['payroll', 'payout', 'pay stub', 'team pay', 'salary', 'wages'],
            'Open Team Member Payouts',
            url_for('worker_payments', client_id=client_id),
        ),
        assistant_topic(
            'calendar',
            'Stay ahead of deadlines',
            'Use the calendar as a working planning tool instead of a decorative page.',
            'The Calendar combines business reminders, IRS dates, payment timing, and custom reminders. Use it as your forward-looking control panel, then keep custom additions tight so the automatic deadlines stay visible.',
            ['calendar', 'deadline', 'dates', 'schedule', 'reminder', 'irs dates'],
            'Open Calendar',
            url_for('business_calendar', client_id=client_id),
        ),
        assistant_topic(
            'benefits',
            'Review benefits and employer obligations',
            'Understand benefit opportunities and compliance responsibilities.',
            'Benefits & Obligations explains the employer-side rules, benefit opportunities, and official reference links that matter when you are deciding whether to add health, retirement, or other structured benefits.',
            ['benefits', 'health', 'retirement', 'obligations', 'aca', 'hsa', 'fsa'],
            'Open Benefits & Obligations',
            url_for('benefits_obligations', client_id=client_id),
        ),
        assistant_topic(
            'reports',
            'Turn activity into reporting',
            'Use reports when you need summary-level visibility instead of record-by-record review.',
            'Reports help you step back from daily entry work and see the business at a higher level. When you need totals, patterns, and cleaner presentation, Reports is the right place to go next.',
            ['report', 'summary', 'totals', 'insights', 'overview report'],
            'Open Reports',
            url_for('reports', client_id=client_id),
        ),
        assistant_topic(
            'welcome_center',
            'Use the welcome center as a guide',
            'Start with the onboarding-style page if you want the system explained clearly.',
            'Welcome Center is the calm starting point for new business users. It explains the workspace, introduces how-to videos, and gives a structured path so the software feels guided instead of overwhelming.',
            ['welcome', 'videos', 'how to', 'new user', 'onboarding'],
            'Open Welcome Center',
            url_for('welcome_center', client_id=client_id),
        ),
    ]


def admin_assistant_topics(active_client, current_mode: str) -> list[dict]:
    topics = [
        assistant_topic(
            'admin_workspace',
            'Work faster from the administrator dashboard',
            'Use the admin side as the control surface for all businesses, billing, and onboarding.',
            'The Administrator Dashboard is designed to help you supervise business setup, payment posture, workspace activity, and alerts without dropping into every screen manually. Start there when you need system-wide visibility.',
            ['admin', 'dashboard', 'overview', 'workspace', 'administrator'],
            'Open Administrator Dashboard',
            url_for('cpa_dashboard'),
        ),
        assistant_topic(
            'businesses',
            'Manage business records cleanly',
            'Search, fold, archive, reactivate, and organize business records without losing history.',
            'Businesses is the record-management center. Use it to keep active businesses organized, archive them safely instead of destroying them, and reactivate them later when they return.',
            ['business', 'profile', 'archive', 'reactivate', 'delete business'],
            'Open Businesses',
            url_for('clients'),
        ),
        assistant_topic(
            'business_users',
            'Control logins, invites, and onboarding',
            'Manage direct logins, prospect invites, and onboarding status from one console.',
            'Business Users is where you handle business logins, invite delivery history, prospect invites, and the point where a new business moves from invited to fully onboarded.',
            ['invite', 'login', 'user', 'prospect', 'onboarding', 'email invite'],
            'Open Business Users',
            url_for('client_users'),
        ),
        assistant_topic(
            'email_settings',
            'Keep email delivery stable',
            'Save SMTP settings, test delivery, and troubleshoot invite and welcome email issues.',
            'Email Settings is the trust layer for invite, welcome, rejoin, and reset messages. Use it to save the SMTP profile, test delivery, and verify that LedgerFlow can actually send the emails the platform depends on.',
            ['email', 'smtp', 'invite failed', 'welcome email', 'mail'],
            'Open Email Settings',
            url_for('email_settings'),
        ),
        assistant_topic(
            'invite_delivery',
            'Track invites and rejoin outreach',
            'Review invite history, email previews, and where prospects or archived businesses sit in the pipeline.',
            'Invite delivery is now a real admin pipeline in LedgerFlow. You can review sent, failed, accepted, prospect, and rejoin activity without losing visibility into what was actually delivered.',
            ['invite delivery', 'email history', 'rejoin', 'preview', 'accepted', 'failed'],
            'Open Business Users',
            url_for('client_users'),
        ),
        assistant_topic(
            'billing_setup',
            'Configure business billing from admin',
            'Handle subscription setup, payment collection posture, and administrator fees.',
            'When a business needs subscription changes, fee setup, or payment collection guidance, use the billing controls from the administrator side so the business sees a calmer, cleaner workspace.',
            ['billing setup', 'subscription setup', 'admin fee', 'payment method', 'charge'],
            'Open Administrator Dashboard',
            url_for('cpa_dashboard'),
        ),
        assistant_topic(
            'admin_calendar',
            'Use the admin calendar strategically',
            'Keep system-wide timing, reminders, and tax planning visible without turning the dashboard into clutter.',
            'The Administrator Calendar is for deadline control across the portfolio, not just decoration. Use it to stay ahead of tax timing, invite follow-up, fee cycles, and the reminder layer that affects multiple businesses.',
            ['calendar', 'deadline', 'portfolio', 'tax dates', 'admin calendar'],
            'Open Calendar',
            url_for('admin_calendar'),
        ),
        assistant_topic(
            'admin_tasks',
            'Work through operational admin tasks',
            'Use Admin Tasks as the practical action list for cleanup, follow-up, and operational work.',
            'Admin Tasks is where operational follow-through belongs when it should not be scattered across notes or memory. It is the structured place for actions that keep the system healthy.',
            ['admin tasks', 'todo', 'follow up', 'operations', 'task'],
            'Open Admin Tasks',
            url_for('admin_tasks'),
        ),
    ]
    if current_mode == 'business' and active_client:
        topics.extend([
            assistant_topic(
                'overview',
                'Review this business workspace as admin',
                'Drop into one business and work in context without losing admin control.',
                f'You are viewing {active_client["business_name"]} in business-workspace mode. Use this when you need to see the business exactly the way the business would, while still keeping a clean path back to the administrator side.',
                ['business workspace', 'view as business', 'switch business', 'admin view'],
                'Open Business Workspace',
                url_for('dashboard', client_id=active_client['id']),
            ),
            assistant_topic(
                'archive_rejoin',
                'Archive and recover businesses safely',
                'Preserve history, send rejoin invites, and recover access without destructive deletes.',
                'LedgerFlow now treats archived businesses as preserved records, not throwaway data. Archive when a business leaves, then use rejoin invites and restore access when they return.',
                ['archive', 'reactivate', 'rejoin', 'restore access', 'inactive business'],
                'Open Businesses',
                url_for('clients'),
            ),
        ])
    return topics


def worker_assistant_topics() -> list[dict]:
    return [
        assistant_topic(
            'time_summary',
            'Read your time summary clearly',
            'Use Time Summary to confirm what the system is recording for your work hours.',
            'Time Summary is the fastest way to verify what has been logged for you. If something looks off, this is the first place to review before you ask a manager about pay or schedule questions.',
            ['time', 'hours', 'summary', 'worked', 'clock'],
            'Open Time Summary',
            url_for('worker_time_summary'),
        ),
        assistant_topic(
            'pay_stubs',
            'Understand your pay stub',
            'Review gross pay, deductions, net pay, and year-to-date figures.',
            'Pay Stubs shows how your payment was built, including gross pay, deductions when applicable, and net pay. Use it when you need the actual payment breakdown instead of a simple payment note.',
            ['pay stub', 'pay', 'net', 'gross', 'deduction', 'wages'],
            'Open Pay Stubs',
            url_for('worker_pay_stubs'),
        ),
        assistant_topic(
            'schedule',
            'Check your schedule',
            'Use Schedule to see upcoming work expectations and timing.',
            'Schedule is the clean place to confirm upcoming work. Check it before requesting changes so you have the same reference point your manager is using.',
            ['schedule', 'shift', 'calendar', 'when do i work'],
            'Open Schedule',
            url_for('worker_schedule'),
        ),
        assistant_topic(
            'time_off',
            'Request time off correctly',
            'Use the Time Off area instead of sending loose messages when you need structured approval.',
            'Time Off Request keeps requests organized and visible to the business. Use it when you need a cleaner process than a text or casual message.',
            ['time off', 'pto', 'vacation', 'request leave', 'day off'],
            'Open Time Off Request',
            url_for('worker_time_off'),
        ),
        assistant_topic(
            'notices',
            'Review policies and notices',
            'Keep up with business notices, portal policies, and updates from the company.',
            'Policies & Notices is the place for business updates that should stay visible and findable. If the company posts a notice, this is the record to review later.',
            ['notice', 'policy', 'document', 'announcement', 'rules'],
            'Open Policies & Notices',
            url_for('worker_notices'),
        ),
        assistant_topic(
            'manager_messages',
            'Use manager messaging effectively',
            'Messenger is designed for quick back-and-forth while you stay on the page you are already using.',
            'The portal messenger stays available in the corner so you do not have to leave the page you are working on. Use it for focused updates, clarifications, and payroll or schedule questions that need a direct thread.',
            ['message', 'manager', 'chat', 'messenger', 'contact manager'],
            'Open Manager Messenger',
            url_for('worker_messages'),
        ),
    ]


def shell_assistant_context(user, worker, active_client, current_mode: str):
    endpoint = request.endpoint or ''
    ai_cfg = ai_assistant_config()
    if worker:
        display_name = assistant_first_name(worker['name'])
        topics = ordered_assistant_topics(worker_assistant_topics(), endpoint)
        page_label = assistant_page_label(endpoint)
        primary_topic = topics[0] if topics else None
        return {
            'enabled': True,
            'role': 'worker',
            'display_name': display_name,
            'title': ai_cfg.get('assistant_label') or 'LedgerFlow Guide AI',
            'subtitle': 'Voice-ready help that stays with you while you move through the Team Member Portal.',
            'greeting': f'Hello, {display_name}. How can I help you today?',
            'context_label': f'Currently on {page_label} for {worker["business_name"]}.',
            'topics': topics,
            'quick_topics': topics[:4],
            'guided_topics': topics[:3],
            'primary_topic': primary_topic,
            'secondary_topics': topics[1:4],
            'page_label': page_label,
            'page_brief': assistant_page_brief(page_label, topics),
            'capabilities': assistant_capabilities('worker'),
            'starter_questions': assistant_starter_questions('worker', topics),
            'live_enabled': ai_cfg.get('configured', False),
        }

    if not user:
        return {'enabled': False}

    display_name = assistant_first_name(user['full_name'])
    page_label = assistant_page_label(endpoint)
    if user['role'] == 'admin':
        topics = ordered_assistant_topics(admin_assistant_topics(active_client, current_mode), endpoint)
        context_label = (
            f'Currently on {page_label} for {active_client["business_name"]}.'
            if active_client and current_mode == 'business'
            else f'Currently on {page_label}.'
        )
    else:
        topics = ordered_assistant_topics(business_assistant_topics(active_client), endpoint)
        context_label = f'Currently on {page_label} for {active_client["business_name"]}.'
    primary_topic = topics[0] if topics else None

    return {
        'enabled': True,
        'role': 'admin' if user['role'] == 'admin' else 'client',
        'display_name': display_name,
        'title': ai_cfg.get('assistant_label') or 'LedgerFlow Guide AI',
        'subtitle': 'Context-aware product help grounded in the page you are working on right now.',
        'greeting': f'Hello, {display_name}. How can I help you today?',
        'context_label': context_label,
        'topics': topics,
        'quick_topics': topics[:4],
        'guided_topics': topics[:3],
        'primary_topic': primary_topic,
        'secondary_topics': topics[1:4],
        'page_label': page_label,
        'page_brief': assistant_page_brief(page_label, topics),
        'capabilities': assistant_capabilities('admin' if user['role'] == 'admin' else 'client'),
        'starter_questions': assistant_starter_questions('admin' if user['role'] == 'admin' else 'client', topics),
        'live_enabled': ai_cfg.get('configured', False),
    }


@app.before_request
def touch_current_user_presence():
    uid = session.get('user_id')
    worker_id = session.get('worker_id')
    if not uid and not worker_id:
        return
    try:
        with get_conn() as conn:
            if uid:
                conn.execute('UPDATE users SET last_seen_at=? WHERE id=?', (datetime.now().isoformat(timespec="seconds"), uid))
            if worker_id:
                conn.execute('UPDATE workers SET portal_last_seen_at=? WHERE id=?', (datetime.now().isoformat(timespec="seconds"), worker_id))
            conn.commit()
    except sqlite3.Error:
        if worker_id:
            session.pop('worker_id', None)


@app.before_request
def auto_send_due_prospect_followups():
    user = current_user()
    if not user or user['role'] != 'admin' or request.method != 'GET':
        return
    endpoint = request.endpoint or ''
    if endpoint in {'static', 'email_open_tracking', 'email_click_tracking'}:
        return
    last_run = parse_datetime_value(session.get('prospect_followup_last_run', ''))
    if last_run and (datetime.now() - last_run) < timedelta(minutes=15):
        return
    try:
        process_due_prospect_followups(triggered_by_user_id=user['id'])
    except Exception:
        pass
    session['prospect_followup_last_run'] = now_iso()


@app.before_request
def enforce_business_onboarding_gate():
    user = current_user()
    if not user or user['role'] != 'client':
        return
    endpoint = request.endpoint or ''
    allowed = {'business_onboarding', 'business_comeback', 'logout', 'static', 'help_center', 'irs_tips', 'forgot_password', 'reset_password'}
    if endpoint in allowed:
        return
    if endpoint == 'welcome_center' and user_has_trial_offer(user):
        return
    if user_requires_business_onboarding(user):
        return redirect(url_for('business_onboarding'))
    if client_access_issue_for_user(user):
        return redirect(url_for('business_comeback'))


def current_mode_for_request(user) -> str:
    if not user:
        return 'guest'
    workspace_requested = str(request.values.get('workspace', '') or '').strip().lower() in {'1', 'true', 'yes', 'on'}
    if request.endpoint == 'clients' and (user['role'] != 'admin' or workspace_requested):
        return 'business'
    if request.endpoint in {'clients', 'client_users', 'client_user_email_preview', 'cpa_dashboard', 'admin_calendar', 'admin_tasks', 'email_settings', 'ai_guide_settings'}:
        return 'cpa'
    return 'business'


def active_client_for_request(user):
    if not user:
        return None
    current_mode = current_mode_for_request(user)
    if current_mode == 'cpa':
        return None
    cid = request.values.get('client_id', type=int) if user['role'] == 'admin' else user['client_id']
    with get_conn() as conn:
        if not cid and user['role'] == 'admin':
            rows = conn.execute("SELECT * FROM clients WHERE COALESCE(record_status,'active')='active' ORDER BY business_name").fetchall()
            if rows:
                cid = rows[0]['id']
        if not cid:
            return None
        return conn.execute('SELECT * FROM clients WHERE id=?', (cid,)).fetchone()


@app.context_processor
def inject_globals():
    user = current_user()
    worker = current_worker()
    clients = []
    default_client_id = ''
    active_client = None
    current_mode = 'guest'
    if user:
        with get_conn() as conn:
            if user['role'] == 'admin':
                clients = conn.execute("SELECT * FROM clients WHERE COALESCE(record_status,'active')='active' ORDER BY business_name").fetchall()
            elif user['client_id']:
                c = conn.execute('SELECT * FROM clients WHERE id=?', (user['client_id'],)).fetchone()
                clients = [c] if c else []
        default_client_id = user['client_id'] if user['role'] == 'client' else (clients[0]['id'] if clients else '')
        current_mode = current_mode_for_request(user)
        if current_mode == 'business':
            cid = request.values.get('client_id', type=int) if user['role'] == 'admin' else user['client_id']
            if not cid and clients:
                cid = clients[0]['id']
            if cid:
                with get_conn() as conn:
                    active_client = conn.execute('SELECT * FROM clients WHERE id=?', (cid,)).fetchone()
    active_review = latest_review_request(active_client['id']) if active_client else None
    pending_alert_count = len(pending_review_alerts()) if user and user['role'] == 'admin' else 0
    shell_messenger = internal_shell_messenger_context(user, active_client, clients) if user else {'enabled': False}
    worker_shell_messenger = worker_shell_messenger_context(worker) if worker else {'enabled': False}
    assistant_visible = ai_guide_visible()
    shell_assistant = shell_assistant_context(user, worker, active_client, current_mode) if assistant_visible else {'enabled': False}
    current_language = current_language_code(user, worker, active_client)
    def tr(text: str, **kwargs) -> str:
        return translate_text(text, current_language, **kwargs)
    return {
        'current_user': user,
        'current_worker_user': worker,
        'all_clients': clients,
        'default_client_id': default_client_id,
        'today': date.today().isoformat(),
        'app_name': APP_NAME,
        'app_subtitle': APP_SUBTITLE,
        'brand_tagline': BRAND_TAGLINE,
        'brand_logo_url': static_asset_url(BRAND_LOGO_FILENAME),
        'brand_mark_url': static_asset_url(BRAND_MARK_FILENAME),
        'irs_mileage_rate': IRS_MILEAGE_RATE,
        'current_mode': current_mode,
        'active_client': active_client,
        'active_business_color': business_color(active_client['id']) if active_client else '#0f766e',
        'active_review': active_review,
        'pending_alert_count': pending_alert_count,
        'app_base_url': configured_base_url(),
        'shell_messenger': shell_messenger,
        'worker_shell_messenger': worker_shell_messenger,
        'shell_assistant': shell_assistant,
        'ai_guide_visible': assistant_visible,
        'subscription_tiers': subscription_tier_view_data(),
        'subscription_tier_map': subscription_tier_view_map(),
        'effective_service_level': effective_service_level,
        'effective_service_level_label': effective_service_level_label,
        'premium_sales_access_enabled': premium_sales_access_enabled,
        'access_level_override_active': access_level_override_active,
        'service_level_access_options': service_level_access_options(),
        'current_request_path': current_request_path(),
        'current_language': current_language,
        'language_options': language_options(),
        'tr': tr,
    }


@app.context_processor
def inject_static_asset_version():
    def static_asset_version(filename: str) -> int:
        return static_asset_version_value(filename)

    return {'static_asset_version': static_asset_version}


@app.route('/')
def index():
    user = current_user()
    worker = current_worker()
    if worker and not user:
        return redirect(url_for('worker_time_summary'))
    if not user:
        return redirect(url_for('login'))
    if user['role'] == 'client' and user_requires_business_onboarding(user):
        return redirect(url_for('business_onboarding'))
    return redirect(url_for('cpa_dashboard' if user['role']=='admin' else 'dashboard'))


@app.route('/trust-and-policies')
def trust_center():
    return render_template('trust_center.html')


@app.route('/set-language', methods=['POST'])
def set_language():
    language = normalize_language(request.form.get('preferred_language'))
    session['preferred_language'] = language
    session['language_override_active'] = 1
    quiet = request.form.get('quiet') in {'1', 'true', 'on', 'yes'}
    user = current_user()
    worker = current_worker()
    if user:
        with get_conn() as conn:
            conn.execute('UPDATE users SET preferred_language=? WHERE id=?', (language, user['id']))
            conn.commit()
    elif worker:
        with get_conn() as conn:
            conn.execute('UPDATE workers SET preferred_language=? WHERE id=?', (language, worker['id']))
            conn.commit()
    if not quiet:
        flash(
            translate_text(
                'Language saved: {language_label}.',
                language,
                language_label=dict(LANGUAGE_OPTIONS).get(language, 'English'),
            ),
            'success',
        )
    return redirect(safe_next_path(request.form.get('next'), '/main-portal'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    setup_required = not admin_user_exists()
    if request.method == 'POST':
        selected_language = normalize_language(request.form.get('preferred_language') or session.get('preferred_language'))
        session['preferred_language'] = selected_language
        if setup_required:
            action = request.form.get('action', 'create_admin').strip().lower()
            if action == 'create_admin':
                full_name = request.form.get('full_name', '').strip()
                email = request.form.get('email', '').strip().lower()
                password = request.form.get('password', '').strip()
                confirm_password = request.form.get('confirm_password', '').strip()
                if not full_name:
                    flash(translate_text('Full name is required.', selected_language), 'error')
                elif not email:
                    flash(translate_text('Email is required.', selected_language), 'error')
                elif len(password) < 8:
                    flash(translate_text('Password must be at least 8 characters.', selected_language), 'error')
                elif password != confirm_password:
                    flash(translate_text('Passwords do not match.', selected_language), 'error')
                else:
                    with get_conn() as conn:
                        if conn.execute("SELECT 1 FROM users WHERE lower(email)=?", (email,)).fetchone():
                            flash(translate_text('Email already exists.', selected_language), 'error')
                        else:
                            conn.execute(
                                'INSERT INTO users (email, password_hash, full_name, role, client_id, preferred_language) VALUES (?,?,?,?,?,?)',
                                (email, generate_password_hash(password), full_name, 'admin', None, selected_language)
                            )
                            conn.commit()
                            flash(translate_text('Administrator account created. Sign in below.', selected_language), 'success')
                            return redirect(url_for('login'))
        else:
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            with get_conn() as conn:
                user = conn.execute('SELECT * FROM users WHERE lower(email)=?', (email,)).fetchone()
                if user and check_password_hash(user['password_hash'], password):
                    client = None
                    if user['role'] == 'client' and user['client_id']:
                        client = conn.execute(
                            'SELECT id, trial_offer_days, preferred_language FROM clients WHERE id=?',
                            (user['client_id'],)
                        ).fetchone()
                    session.clear()
                    session['user_id'] = user['id']
                    session['preferred_language'] = normalize_language(
                        (user['preferred_language'] if user else '')
                        or (client['preferred_language'] if client else '')
                        or selected_language
                    )
                    if user['role'] == 'client' and user_requires_business_onboarding(user):
                        return redirect(url_for('business_onboarding'))
                    if user['role'] == 'client':
                        issue = client_access_issue_for_user(user)
                        if issue:
                            return redirect(url_for('business_comeback'))
                        if client and int(client['trial_offer_days'] or 0) > 0:
                            return redirect(url_for('welcome_center', client_id=user['client_id']))
                    return redirect(url_for('cpa_dashboard' if user['role']=='admin' else 'dashboard'))

                workers = conn.execute(
                    '''SELECT w.*, c.business_name, c.subscription_status client_subscription_status, c.record_status client_record_status
                       FROM workers w
                       JOIN clients c ON c.id = w.client_id
                       WHERE lower(COALESCE(w.email,''))=?
                       ORDER BY CASE COALESCE(w.portal_approval_status,'approved')
                                  WHEN 'approved' THEN 0
                                  WHEN 'pending' THEN 1
                                  WHEN 'needs_correction' THEN 2
                                  ELSE 3
                                END,
                                w.id DESC''',
                    (email,)
                ).fetchall()
                approved_workers = [
                    w for w in workers
                    if worker_portal_access_allowed(w)
                ]
                valid_worker = None
                for worker in approved_workers:
                    valid = False
                    if worker['portal_password_hash']:
                        valid = check_password_hash(worker['portal_password_hash'], password)
                    else:
                        valid = worker_default_password_matches(worker, password)
                        if valid:
                            conn.execute(
                                'UPDATE workers SET portal_password_hash=? WHERE id=?',
                                (generate_password_hash(password), worker['id'])
                            )
                            conn.commit()
                    if valid:
                        valid_worker = worker
                        break

                if valid_worker:
                    session.clear()
                    session['worker_id'] = valid_worker['id']
                    session['preferred_language'] = normalize_language(valid_worker['preferred_language'] or selected_language)
                    return redirect(url_for('worker_time_summary'))

            has_pending = any(
                int(w['portal_access_enabled'] or 0) == 1 and (w['portal_approval_status'] or 'approved') == 'pending'
                for w in workers
            ) if 'workers' in locals() else False
            has_needs_correction = any((w['portal_approval_status'] or '') == 'needs_correction' for w in workers) if 'workers' in locals() else False
            has_terminated = any((w['status'] or 'active') != 'active' for w in workers) if 'workers' in locals() else False
            has_approved = bool(approved_workers) if 'approved_workers' in locals() else False
            if has_pending and not has_approved:
                flash(translate_text('Worker portal access is pending administrator approval.', selected_language), 'error')
            elif has_needs_correction and not has_approved:
                flash(translate_text('Worker portal access needs correction from the business before you can sign in.', selected_language), 'error')
            elif has_terminated and not has_approved:
                flash(translate_text('Team member portal access is no longer active.', selected_language), 'error')
            else:
                flash(translate_text('Invalid email or password.', selected_language), 'error')
    return render_template('login.html', setup_required=setup_required)


@app.route('/create-account')
def create_account_info():
    return render_template('create_account.html')


@app.route('/main-portal', methods=['GET', 'POST'])
def main_portal():
    return login()


@app.route('/production-import', methods=['GET', 'POST'])
def production_import():
    if not production_import_enabled():
        abort(404)
    error_text = ''
    success_text = ''
    backup_path = ''
    written_files: list[str] = []
    if request.method == 'POST':
        supplied_key = (request.form.get('import_key') or '').strip()
        expected_key = production_import_key()
        if not expected_key:
            error_text = 'Production import key is not configured.'
        elif not secrets.compare_digest(supplied_key, expected_key):
            error_text = 'Import key is incorrect.'
        else:
            bundle = request.files.get('migration_bundle')
            filename = (bundle.filename or '').strip() if bundle else ''
            if not bundle or not filename.lower().endswith('.zip'):
                error_text = 'Upload the Render migration ZIP file.'
            else:
                with tempfile.TemporaryDirectory() as temp_dir:
                    bundle_path = Path(temp_dir) / 'render_migration_bundle.zip'
                    bundle.save(bundle_path)
                    try:
                        written_files, backup_dir = apply_migration_bundle(bundle_path)
                        backup_path = str(backup_dir) if backup_dir else ''
                        success_text = 'Migration imported successfully. Restart the Render service now so the imported database and secret key are loaded cleanly, then open /production-import-status to verify the live database.'
                    except Exception as exc:
                        error_text = str(exc)
    return render_template_string(
        """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LedgerFlow Production Import</title>
  <style>
    body { margin: 0; font-family: Georgia, 'Times New Roman', serif; background: #1F1F1F; color: #F3EFE7; }
    .shell { max-width: 760px; margin: 48px auto; padding: 32px; background: rgba(243,239,231,0.06); border: 1px solid rgba(184,173,160,0.28); border-radius: 22px; box-shadow: 0 24px 60px rgba(0,0,0,0.32); }
    h1 { margin: 0 0 12px; font-size: 32px; }
    p, li, label { color: #D8D2C8; line-height: 1.6; }
    .eyebrow { text-transform: uppercase; letter-spacing: 0.18em; font-size: 12px; color: #B8ADA0; margin-bottom: 12px; }
    .notice { padding: 14px 16px; border-radius: 14px; margin: 18px 0; }
    .error { background: rgba(158,76,76,0.24); border: 1px solid rgba(255,155,155,0.28); color: #ffe1de; }
    .success { background: rgba(105,132,94,0.24); border: 1px solid rgba(170,214,161,0.28); color: #efffe7; }
    .card { background: rgba(255,255,255,0.03); border: 1px solid rgba(184,173,160,0.2); border-radius: 18px; padding: 20px; margin-top: 20px; }
    input[type=password], input[type=file] { width: 100%; padding: 14px 16px; border-radius: 12px; border: 1px solid rgba(184,173,160,0.35); background: rgba(243,239,231,0.96); color: #1F1F1F; box-sizing: border-box; margin-top: 8px; margin-bottom: 18px; }
    button { background: #8A7A67; color: #F3EFE7; border: none; border-radius: 999px; padding: 14px 22px; font-weight: 700; cursor: pointer; }
    code { background: rgba(255,255,255,0.08); padding: 2px 6px; border-radius: 6px; }
  </style>
</head>
<body>
  <div class="shell">
    <div class="eyebrow">LedgerFlow Production Import</div>
    <h1>Upload your live data bundle</h1>
    <p>Use this one-time page only after your Render persistent disk is attached. Upload the ZIP bundle from your Desktop to move your real businesses, team members, email settings, and login data into production.</p>
    {% if error_text %}<div class="notice error">{{ error_text }}</div>{% endif %}
    {% if success_text %}<div class="notice success">{{ success_text }}</div>{% endif %}
    <div class="card">
      <form method="post" enctype="multipart/form-data">
        <label for="import_key">Production Import Key</label>
        <input id="import_key" name="import_key" type="password" autocomplete="off" required>
        <label for="migration_bundle">Render Migration ZIP</label>
        <input id="migration_bundle" name="migration_bundle" type="file" accept=".zip" required>
        <button type="submit">Import Production Data</button>
      </form>
    </div>
    <div class="card">
      <p><strong>Bundle must contain:</strong></p>
      <ul>
        <li><code>rds_core_web.db</code></li>
        <li><code>email_runtime_config.json</code></li>
        <li><code>.local_secret_key</code></li>
      </ul>
      {% if written_files %}
      <p><strong>Imported now:</strong> {{ written_files|join(', ') }}</p>
      {% endif %}
      {% if backup_path %}
      <p><strong>Backup created on Render:</strong> <code>{{ backup_path }}</code></p>
      {% endif %}
      <p>After a successful import, restart the Render service once so the imported database and secret key are picked up cleanly.</p>
    </div>
  </div>
</body>
</html>""",
        error_text=error_text,
        success_text=success_text,
        backup_path=backup_path,
        written_files=written_files,
    )


@app.route('/production-import-status')
def production_import_status():
    if not production_import_enabled():
        abort(404)
    snapshot = production_import_status_snapshot()
    return render_template_string(
        """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LedgerFlow Production Import Status</title>
  <style>
    body { margin: 0; font-family: Georgia, 'Times New Roman', serif; background: #141B2D; color: #F4F1E8; }
    .shell { max-width: 880px; margin: 48px auto; padding: 32px; background: rgba(26,34,54,0.94); border: 1px solid rgba(116,130,155,0.38); border-radius: 22px; box-shadow: 0 26px 60px rgba(34,37,43,0.35); }
    h1 { margin: 0 0 10px; font-size: 30px; }
    p, li { color: #E6E7E8; line-height: 1.6; }
    .eyebrow { text-transform: uppercase; letter-spacing: .16em; font-size: 12px; color: #74829B; margin-bottom: 12px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit,minmax(180px,1fr)); gap: 14px; margin: 20px 0; }
    .card { background: rgba(255,255,255,0.04); border: 1px solid rgba(116,130,155,0.28); border-radius: 18px; padding: 16px; }
    .label { font-size: 12px; text-transform: uppercase; letter-spacing: .08em; color: #74829B; margin-bottom: 8px; }
    .metric { font-size: 28px; font-weight: 700; color: #F4F1E8; }
    code { display:block; white-space:pre-wrap; word-break:break-word; background: rgba(255,255,255,0.06); color: #E6E7E8; border-radius: 12px; padding: 12px; margin-top: 8px; }
    .ok { color: #9dd29f; }
    .bad { color: #ffb4b4; }
  </style>
</head>
<body>
  <div class="shell">
    <div class="eyebrow">LedgerFlow Production Import Status</div>
    <h1>Live database verification</h1>
    <p>Use this page after import and restart. If <strong>Admin Count</strong> is still <strong>0</strong>, this Render service is still reading an empty database.</p>
    <div class="grid">
      <div class="card"><div class="label">Admin Count</div><div class="metric">{{ snapshot.admin_count }}</div></div>
      <div class="card"><div class="label">Users</div><div class="metric">{{ snapshot.user_count }}</div></div>
      <div class="card"><div class="label">Businesses</div><div class="metric">{{ snapshot.client_count }}</div></div>
      <div class="card"><div class="label">Team Members</div><div class="metric">{{ snapshot.worker_count }}</div></div>
    </div>
    <div class="card">
      <div class="label">Database File</div>
      <div class="{{ 'ok' if snapshot.db_exists else 'bad' }}">{{ 'Present' if snapshot.db_exists else 'Missing' }}</div>
      <code>{{ snapshot.db_path }}</code>
      <div class="label" style="margin-top:12px">Database Size</div>
      <div>{{ snapshot.db_size }} bytes</div>
    </div>
    <div class="card">
      <div class="label">Data Directory</div>
      <code>{{ snapshot.data_dir }}</code>
      <div class="label" style="margin-top:12px">Environment DATA_DIR</div>
      <code>{{ snapshot.data_dir_env or '(not set)' }}</code>
      <div class="label" style="margin-top:12px">Environment DATABASE_PATH</div>
      <code>{{ snapshot.database_path_env or '(not set)' }}</code>
    </div>
    <div class="card">
      <div class="label">Email Config File</div>
      <div class="{{ 'ok' if snapshot.email_config_exists else 'bad' }}">{{ 'Present' if snapshot.email_config_exists else 'Missing' }}</div>
      <code>{{ snapshot.email_config_path }}</code>
      <div class="label" style="margin-top:12px">Local Secret Key</div>
      <div class="{{ 'ok' if snapshot.secret_key_exists else 'bad' }}">{{ 'Present' if snapshot.secret_key_exists else 'Missing' }}</div>
    </div>
    {% if snapshot.db_error %}
    <div class="card">
      <div class="label">Database Error</div>
      <code>{{ snapshot.db_error }}</code>
    </div>
    {% endif %}
  </div>
</body>
</html>""",
        snapshot=snapshot,
    )


@app.route('/business-comeback')
@login_required
def business_comeback():
    user = current_user()
    if not user or user['role'] != 'client':
        return redirect(url_for('main_portal'))
    issue = client_access_issue_for_user(user)
    if not issue:
        return redirect(url_for('dashboard'))
    return render_template('business_comeback.html', user=user, issue=issue)


@app.route('/worker-login', methods=['GET', 'POST'])
def worker_login():
    if request.method == 'POST':
        selected_language = normalize_language(request.form.get('preferred_language') or session.get('preferred_language'))
        session['preferred_language'] = selected_language
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()
        with get_conn() as conn:
            workers = conn.execute(
                '''SELECT w.*, c.business_name, c.contact_name business_contact_name,
                          c.subscription_status client_subscription_status, c.record_status client_record_status
                   FROM workers w
                   JOIN clients c ON c.id = w.client_id
                   WHERE lower(COALESCE(w.email,''))=?
                   ORDER BY CASE COALESCE(w.portal_approval_status,'approved')
                              WHEN 'approved' THEN 0
                              WHEN 'pending' THEN 1
                              WHEN 'needs_correction' THEN 2
                              ELSE 3
                            END,
                            w.id DESC''',
                (email,)
            ).fetchall()
            approved_workers = [
                w for w in workers
                if worker_portal_access_allowed(w)
            ]
            valid_worker = None
            for worker in approved_workers:
                valid = False
                if worker['portal_password_hash']:
                    valid = check_password_hash(worker['portal_password_hash'], password)
                else:
                    valid = worker_default_password_matches(worker, password)
                    if valid:
                        conn.execute('UPDATE workers SET portal_password_hash=? WHERE id=?', (generate_password_hash(password), worker['id']))
                        conn.commit()
                if valid:
                    valid_worker = worker
                    break
            if valid_worker:
                session.clear()
                session['worker_id'] = valid_worker['id']
                session['preferred_language'] = normalize_language(valid_worker['preferred_language'] or selected_language)
                return redirect(url_for('worker_time_summary'))

            has_pending = any(
                int(w['portal_access_enabled'] or 0) == 1 and (w['portal_approval_status'] or 'approved') == 'pending'
                for w in workers
            )
            has_needs_correction = any((w['portal_approval_status'] or '') == 'needs_correction' for w in workers)
            has_terminated = any((w['status'] or 'active') != 'active' for w in workers)
            has_approved = bool(approved_workers)
            if has_pending and not has_approved:
                flash(translate_text('Team member portal access is pending administrator approval.', selected_language), 'error')
            elif has_needs_correction and not has_approved:
                flash(translate_text('Team member portal access needs correction before you can sign in.', selected_language), 'error')
            elif has_terminated and not has_approved:
                flash(translate_text('Team member portal access is no longer active.', selected_language), 'error')
            else:
                flash(translate_text('Invalid team member email or password.', selected_language), 'error')
    return render_template('worker_login.html')


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        selected_language = normalize_language(request.form.get('preferred_language') or session.get('preferred_language'))
        session['preferred_language'] = selected_language
        with get_conn() as conn:
            user = conn.execute('SELECT id, role FROM users WHERE lower(email)=?', (email,)).fetchone() if email else None
            approved_worker = conn.execute(
                '''SELECT id
                   FROM workers
                   WHERE lower(COALESCE(email,''))=?
                     AND COALESCE(portal_approval_status,'approved')='approved'
                     AND COALESCE(portal_access_enabled,1)=1
                   ORDER BY id DESC
                   LIMIT 1''',
                (email,)
            ).fetchone() if email else None
            account_kind = None
            account_id = None
            account_label = 'account'
            if user:
                account_kind = 'user'
                account_id = user['id']
                account_label = 'administrator/business account'
            elif approved_worker:
                account_kind = 'worker'
                account_id = approved_worker['id']
                account_label = 'worker portal account'

            if account_kind and account_id:
                token = secrets.token_urlsafe(32)
                expires_at = (datetime.utcnow() + timedelta(hours=1)).isoformat(timespec='seconds')
                conn.execute(
                    "INSERT INTO password_reset_requests (email, account_kind, account_id, token, status, expires_at, requester_ip) VALUES (?,?,?,?,?,?,?)",
                    (email, account_kind, account_id, token, 'pending', expires_at, (request.headers.get('X-Forwarded-For', '') or request.remote_addr or '')[:120])
                )
                conn.commit()
                if smtp_email_ready():
                    try:
                        reset_link = f"{configured_base_url()}{url_for('reset_password', token=token)}"
                        send_password_reset_email(email, reset_link, account_label)
                    except Exception:
                        pass
        flash(
            translate_text(
                'If the email exists in {app_name}, a password reset request has been submitted. Check your email if delivery is enabled, or contact your administrator.',
                selected_language,
                app_name=APP_NAME,
            ),
            'success',
        )
        return redirect(url_for('forgot_password'))
    return render_template('forgot_password.html')


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    with get_conn() as conn:
        reset_row = conn.execute(
            "SELECT * FROM password_reset_requests WHERE token=? AND status='pending' ORDER BY id DESC LIMIT 1",
            (token,)
        ).fetchone()
        selected_language = normalize_language(session.get('preferred_language'))
        if not reset_row:
            flash(translate_text('This reset link is invalid or has already been used.', selected_language), 'error')
            return redirect(url_for('forgot_password'))
        try:
            expires_at = datetime.fromisoformat((reset_row['expires_at'] or '').replace('Z', ''))
        except Exception:
            expires_at = None
        if not expires_at or expires_at < datetime.utcnow():
            conn.execute("UPDATE password_reset_requests SET status='expired' WHERE id=?", (reset_row['id'],))
            conn.commit()
            flash(translate_text('This reset link has expired. Submit a new reset request.', selected_language), 'error')
            return redirect(url_for('forgot_password'))

        if request.method == 'POST':
            selected_language = normalize_language(request.form.get('preferred_language') or session.get('preferred_language'))
            session['preferred_language'] = selected_language
            password = request.form.get('password', '').strip()
            confirm_password = request.form.get('confirm_password', '').strip()
            if len(password) < 8:
                flash(translate_text('Password must be at least 8 characters.', selected_language), 'error')
            elif password != confirm_password:
                flash(translate_text('Passwords do not match.', selected_language), 'error')
            else:
                password_hash = generate_password_hash(password)
                if reset_row['account_kind'] == 'user':
                    conn.execute('UPDATE users SET password_hash=? WHERE id=?', (password_hash, reset_row['account_id']))
                else:
                    conn.execute('UPDATE workers SET portal_password_hash=? WHERE id=?', (password_hash, reset_row['account_id']))
                conn.execute(
                    "UPDATE password_reset_requests SET status='used', used_at=CURRENT_TIMESTAMP WHERE id=?",
                    (reset_row['id'],)
                )
                conn.commit()
                flash(translate_text('Password reset complete. Sign in with your new password.', selected_language), 'success')
                return redirect(url_for('login' if reset_row['account_kind'] == 'user' else 'worker_login'))

    return render_template('reset_password.html', token=token)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('main_portal'))


@app.route('/cpa-dashboard', methods=['GET', 'POST'])
@admin_required
def cpa_dashboard():
    user = current_user()
    selected_id = request.values.get('client_id', type=int)
    if request.method == 'POST':
        action = request.form.get('action', '').strip().lower()
        if action in {'update_subscription_profile', 'add_payment_item', 'update_payment_item', 'update_payment_status', 'cancel_payment_item', 'archive_payment_item', 'add_payment_method', 'update_payment_method', 'delete_payment_method'} and not valid_payment_csrf(request.form.get('csrf_token', '')):
            flash('Your session expired. Refresh the page and try again.', 'error')
            return redirect(url_for('cpa_dashboard', client_id=selected_id))
        with get_conn() as conn:
            if action == 'update_subscription_profile':
                client_id = request.form.get('client_id', type=int)
                client = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone() if client_id else None
                if not client or client['id'] not in visible_client_ids(user):
                    flash('Business not found.', 'error')
                    return redirect(url_for('cpa_dashboard', client_id=selected_id))
                cleaned, errors = validate_subscription_profile_form(request.form)
                if not errors:
                    started_at, canceled_at, paused_at = subscription_status_timestamps(cleaned['subscription_status'], client)
                    conn.execute(
                        '''UPDATE clients
                           SET subscription_plan_code=?, subscription_status=?, subscription_amount=?, subscription_interval=?,
                               subscription_autopay_enabled=?, subscription_next_billing_date=?, subscription_started_at=?,
                               subscription_canceled_at=?, subscription_paused_at=?, default_payment_method_label=?,
                               default_payment_method_status=?, backup_payment_method_label=?, billing_notes=?
                           WHERE id=?''',
                        (
                            cleaned['subscription_plan_code'],
                            cleaned['subscription_status'],
                            cleaned['subscription_amount'],
                            cleaned['subscription_interval'],
                            cleaned['subscription_autopay_enabled'],
                            cleaned['subscription_next_billing_date'],
                            started_at,
                            canceled_at,
                            paused_at,
                            cleaned['default_payment_method_label'],
                            cleaned['default_payment_method_status'],
                            cleaned['backup_payment_method_label'],
                            cleaned['billing_notes'],
                            client_id,
                        )
                    )
                    conn.commit()
                    flash('Subscription billing foundation updated.', 'success')
                else:
                    for error in errors:
                        flash(error, 'error')
                return redirect(url_for('cpa_dashboard', client_id=client_id))
            elif action == 'add_payment_method':
                client_id = request.form.get('client_id', type=int)
                client = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone() if client_id else None
                if not client or client['id'] not in visible_client_ids(user):
                    flash('Business not found.', 'error')
                    return redirect(url_for('cpa_dashboard', client_id=selected_id))
                cleaned, errors = validate_payment_method_form(request.form)
                if not errors:
                    if cleaned['is_default']:
                        conn.execute('UPDATE business_payment_methods SET is_default=0 WHERE client_id=?', (client_id,))
                    if cleaned['is_backup']:
                        conn.execute('UPDATE business_payment_methods SET is_backup=0 WHERE client_id=?', (client_id,))
                    conn.execute(
                        '''INSERT INTO business_payment_methods (client_id, method_type, label, status, is_default, is_backup, holder_name, brand_name, account_last4, expiry_display, account_type, card_number_enc, routing_number_enc, account_number_enc, details_note, created_by_user_id, updated_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (
                            client_id,
                            cleaned['method_type'],
                            cleaned['label'],
                            cleaned['status'],
                            cleaned['is_default'],
                            cleaned['is_backup'],
                            cleaned['holder_name'],
                            cleaned['brand_name'],
                            cleaned['account_last4'],
                            cleaned['expiry_display'],
                            cleaned['account_type'],
                            cleaned['card_number_enc'],
                            cleaned['routing_number_enc'],
                            cleaned['account_number_enc'],
                            cleaned['details_note'],
                            user['id'],
                            datetime.now().isoformat(timespec='seconds'),
                        )
                    )
                    sync_client_payment_method_summary(conn, client_id)
                    conn.commit()
                    flash('Payment method record saved.', 'success')
                else:
                    for error in errors:
                        flash(error, 'error')
                return redirect(url_for('cpa_dashboard', client_id=client_id))
            elif action == 'update_payment_method':
                method_id = request.form.get('payment_method_id', type=int)
                row = conn.execute('SELECT * FROM business_payment_methods WHERE id=?', (method_id,)).fetchone() if method_id else None
                if not row or row['client_id'] not in visible_client_ids(user):
                    flash('Payment method not found.', 'error')
                    return redirect(url_for('cpa_dashboard', client_id=selected_id))
                cleaned, errors = validate_payment_method_form(request.form, existing=row)
                if not errors:
                    if cleaned['is_default']:
                        conn.execute('UPDATE business_payment_methods SET is_default=0 WHERE client_id=?', (row['client_id'],))
                    if cleaned['is_backup']:
                        conn.execute('UPDATE business_payment_methods SET is_backup=0 WHERE client_id=?', (row['client_id'],))
                    conn.execute(
                        '''UPDATE business_payment_methods
                           SET method_type=?, label=?, status=?, is_default=?, is_backup=?, holder_name=?, brand_name=?, account_last4=?, expiry_display=?, account_type=?, card_number_enc=?, routing_number_enc=?, account_number_enc=?, details_note=?, updated_at=?
                           WHERE id=?''',
                        (
                            cleaned['method_type'],
                            cleaned['label'],
                            cleaned['status'],
                            cleaned['is_default'],
                            cleaned['is_backup'],
                            cleaned['holder_name'],
                            cleaned['brand_name'],
                            cleaned['account_last4'],
                            cleaned['expiry_display'],
                            cleaned['account_type'],
                            cleaned['card_number_enc'],
                            cleaned['routing_number_enc'],
                            cleaned['account_number_enc'],
                            cleaned['details_note'],
                            datetime.now().isoformat(timespec='seconds'),
                            method_id,
                        )
                    )
                    sync_client_payment_method_summary(conn, row['client_id'])
                    conn.commit()
                    flash('Payment method updated.', 'success')
                else:
                    for error in errors:
                        flash(error, 'error')
                return redirect(url_for('cpa_dashboard', client_id=row['client_id']))
            elif action == 'delete_payment_method':
                method_id = request.form.get('payment_method_id', type=int)
                row = conn.execute('SELECT * FROM business_payment_methods WHERE id=?', (method_id,)).fetchone() if method_id else None
                if row and row['client_id'] in visible_client_ids(user):
                    conn.execute('DELETE FROM business_payment_methods WHERE id=?', (method_id,))
                    sync_client_payment_method_summary(conn, row['client_id'])
                    conn.commit()
                    flash('Payment method removed.', 'success')
                    return redirect(url_for('cpa_dashboard', client_id=row['client_id']))
                flash('Payment method not found.', 'error')
                return redirect(url_for('cpa_dashboard', client_id=selected_id))
            if action == 'add_payment_item':
                cleaned, errors = validate_payment_item_form(request.form, require_client=True)
                client_id = cleaned['client_id']
                if client_id and client_id not in visible_client_ids(user):
                    errors.append('Selected business is not available.')
                if not errors:
                    conn.execute(
                        '''INSERT INTO business_payment_items (client_id, payment_type, is_admin_fee, collection_method, description, amount_due, status, due_date, payment_link, public_payment_link, payment_instructions, note, cancellation_note, created_by_user_id, paid_at, updated_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (
                            client_id,
                            cleaned['payment_type'],
                            1,
                            cleaned['collection_method'],
                            cleaned['description'],
                            cleaned['amount_due'],
                            cleaned['status'],
                            cleaned['due_date'],
                            cleaned['payment_link'],
                            cleaned['public_payment_link'],
                            cleaned['payment_instructions'],
                            cleaned['note'],
                            cleaned['cancellation_note'],
                            user['id'],
                            payment_paid_at_for_status(cleaned['status']),
                            datetime.now().isoformat(timespec='seconds'),
                        )
                    )
                    conn.commit()
                    flash('Payment item saved.', 'success')
                else:
                    for error in errors:
                        flash(error, 'error')
                return redirect(url_for('cpa_dashboard', client_id=client_id or selected_id))
            elif action == 'update_payment_item':
                item_id = request.form.get('payment_item_id', type=int)
                item = conn.execute('SELECT * FROM business_payment_items WHERE id=?', (item_id,)).fetchone() if item_id else None
                if not item or item['client_id'] not in visible_client_ids(user):
                    flash('Payment item not found.', 'error')
                    return redirect(url_for('cpa_dashboard', client_id=selected_id))
                cleaned, errors = validate_payment_item_form(request.form, require_client=False)
                if not errors:
                    conn.execute(
                        '''UPDATE business_payment_items
                           SET payment_type=?, collection_method=?, description=?, amount_due=?, status=?, due_date=?, payment_link=?, public_payment_link=?, payment_instructions=?, note=?, cancellation_note=?, paid_at=?, updated_at=?
                           WHERE id=?''',
                        (
                            cleaned['payment_type'],
                            cleaned['collection_method'],
                            cleaned['description'],
                            cleaned['amount_due'],
                            cleaned['status'],
                            cleaned['due_date'],
                            cleaned['payment_link'],
                            cleaned['public_payment_link'],
                            cleaned['payment_instructions'],
                            cleaned['note'],
                            cleaned['cancellation_note'],
                            payment_paid_at_for_status(cleaned['status'], item['paid_at'] or ''),
                            datetime.now().isoformat(timespec='seconds'),
                            item_id,
                        )
                    )
                    conn.commit()
                    flash('Payment item updated.', 'success')
                else:
                    for error in errors:
                        flash(error, 'error')
                return redirect(url_for('cpa_dashboard', client_id=item['client_id']))
            elif action == 'update_payment_status':
                item_id = request.form.get('payment_item_id', type=int)
                status = request.form.get('status', 'pending').strip().lower()
                if status not in business_payment_statuses():
                    status = 'pending'
                item = conn.execute('SELECT * FROM business_payment_items WHERE id=?', (item_id,)).fetchone() if item_id else None
                if item and item['client_id'] in visible_client_ids(user):
                    paid_at = payment_paid_at_for_status(status, item['paid_at'] or '')
                    conn.execute('UPDATE business_payment_items SET status=?, paid_at=?, updated_at=? WHERE id=?', (status, paid_at, datetime.now().isoformat(timespec='seconds'), item_id))
                    conn.commit()
                    flash('Payment status updated.', 'success')
                    return redirect(url_for('cpa_dashboard', client_id=item['client_id']))
                flash('Payment item not found.', 'error')
                return redirect(url_for('cpa_dashboard', client_id=selected_id))
            elif action == 'cancel_payment_item':
                item_id = request.form.get('payment_item_id', type=int)
                item = conn.execute('SELECT * FROM business_payment_items WHERE id=?', (item_id,)).fetchone() if item_id else None
                if item and item['client_id'] in visible_client_ids(user):
                    cancellation_note = request.form.get('cancellation_note', '').strip()[:300]
                    conn.execute(
                        '''UPDATE business_payment_items
                           SET status='cancelled', cancellation_note=?, paid_at='', updated_at=?
                           WHERE id=?''',
                        (cancellation_note, datetime.now().isoformat(timespec='seconds'), item_id)
                    )
                    conn.commit()
                    flash('Administrator fee cancelled.', 'success')
                    return redirect(url_for('cpa_dashboard', client_id=item['client_id']))
                flash('Payment item not found.', 'error')
                return redirect(url_for('cpa_dashboard', client_id=selected_id))
            elif action == 'archive_payment_item':
                item_id = request.form.get('payment_item_id', type=int)
                item = conn.execute('SELECT * FROM business_payment_items WHERE id=?', (item_id,)).fetchone() if item_id else None
                if item and item['client_id'] in visible_client_ids(user):
                    conn.execute(
                        'UPDATE business_payment_items SET archived_at=?, updated_at=? WHERE id=?',
                        (datetime.now().isoformat(timespec="seconds"), datetime.now().isoformat(timespec='seconds'), item_id)
                    )
                    conn.commit()
                    flash('Administrator fee archived from the active workspace list.', 'success')
                    return redirect(url_for('cpa_dashboard', client_id=item['client_id']))
                flash('Payment item not found.', 'error')
                return redirect(url_for('cpa_dashboard', client_id=selected_id))

    ids = visible_client_ids(user)
    with get_conn() as conn:
        businesses = conn.execute("SELECT * FROM clients WHERE COALESCE(record_status,'active')='active' ORDER BY business_name").fetchall()
    if ids:
        with get_conn() as conn:
            q_marks = ','.join('?' for _ in ids)
            pending_worker_requests_all = conn.execute(
                f'''SELECT w.*, c.business_name
                    FROM workers w
                    JOIN clients c ON c.id = w.client_id
                    WHERE w.client_id IN ({q_marks})
                      AND COALESCE(w.portal_access_enabled,0)=1
                      AND COALESCE(w.portal_approval_status,'approved')='pending'
                    ORDER BY c.business_name, w.name''',
                tuple(ids)
            ).fetchall()

    if not selected_id and businesses:
        selected_id = businesses[0]['id']
    selected_business = None
    messenger_rows = []
    participants = []
    latest_review = None
    pending_worker_requests = []
    pending_worker_requests_all = []
    selected_payment_methods = []
    if selected_id:
        with get_conn() as conn:
            selected_business = conn.execute('SELECT * FROM clients WHERE id=?', (selected_id,)).fetchone()
            pending_worker_requests = conn.execute(
                '''SELECT w.*
                   FROM workers w
                   WHERE w.client_id=? AND COALESCE(w.portal_access_enabled,0)=1 AND COALESCE(w.portal_approval_status,'approved')='pending'
                   ORDER BY w.name''',
                (selected_id,)
            ).fetchall()
            selected_payment_methods = conn.execute(
                '''SELECT *
                   FROM business_payment_methods
                   WHERE client_id=?
                   ORDER BY is_default DESC, is_backup DESC, updated_at DESC, id DESC''',
                (selected_id,)
            ).fetchall()
        mark_messages_read(selected_id, user['id'])
        messenger_rows = chat_messages(selected_id)
        participants = chat_participants(selected_id)
        latest_review = latest_review_request(selected_id)
    selected_business_payments = business_payment_summary(selected_id) if selected_id else {'rows': [], 'amount_due': 0.0, 'paid_total': 0.0, 'pending_count': 0, 'paid_count': 0, 'cancelled_count': 0}
    return render_template('cpa_dashboard.html', businesses=businesses, totals=cpa_dashboard_summary(user), review_alerts=pending_review_alerts(), selected_client_id=selected_id, selected_business=selected_business, messenger_rows=messenger_rows, participants=participants, latest_review=latest_review, pending_worker_requests=pending_worker_requests, pending_worker_requests_all=pending_worker_requests_all, business_login_counts=per_business_login_counts(visible_client_ids(user)), account_activity_rows=recent_account_activity(visible_client_ids(user), limit=25), chat_unread_count=unread_message_count(selected_id, user['id']) if selected_id else 0, chat_recipients=available_recipients(selected_id, user['id']) if selected_id else [], selected_recipient_id=default_recipient_id(selected_id, user) if selected_id else None, latest_incoming_message=latest_incoming_message(selected_id, user['id']) if selected_id else None, selected_business_payments=selected_business_payments, selected_payment_methods=selected_payment_methods, selected_payment_method_summary=payment_method_summary(selected_payment_methods), payment_statuses=business_payment_statuses(), payment_type_options=payment_type_options(), collection_method_options=collection_method_options(), collection_method_labels=collection_method_label_map(), payment_method_type_options=payment_method_type_options(), payment_method_status_options=payment_method_status_options(), payment_method_type_labels=payment_method_type_label_map(), payment_method_status_labels=payment_method_status_label_map(), subscription_status_options=subscription_status_options(), subscription_status_labels=subscription_status_label_map(), service_level_options=service_level_options(), service_level_labels=service_level_label_map(), suggested_payment_amounts=suggested_payment_amounts_map(), all_payment_items=all_business_payment_items(), payment_csrf_token=payment_csrf_token())




def reminder_types():
    return [
        'EFTPS payment due',
        'Payroll tax deposit due',
        'Form 941 due',
        'Annual report filing',
        'Sales tax filing',
        '1099 deadline',
        'W-2 deadline',
        'Quarterly estimated tax',
        'Custom reminder',
    ]


def _calendar_event(event_date: date, title: str, detail: str = '', tone: str = 'info', source: str = 'system'):
    return {
        'event_date': event_date.isoformat(),
        'title': title,
        'detail': detail,
        'tone': tone,
        'source': source,
    }


def _nth_weekday_of_month(year: int, month: int, weekday: int, occurrence: int) -> date:
    current = date(year, month, 1)
    while current.weekday() != weekday:
        current += timedelta(days=1)
    return current + timedelta(days=7 * (occurrence - 1))


def _last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    import calendar as pycal

    last_day = pycal.monthrange(year, month)[1]
    current = date(year, month, last_day)
    while current.weekday() != weekday:
        current -= timedelta(days=1)
    return current


def _observed_holiday(year: int, month: int, day_value: int) -> date:
    holiday = date(year, month, day_value)
    if holiday.weekday() == 5:
        return holiday - timedelta(days=1)
    if holiday.weekday() == 6:
        return holiday + timedelta(days=1)
    return holiday


def national_holiday_events(year: int):
    holidays = [
        (_observed_holiday(year, 1, 1), 'New Year’s Day'),
        (_nth_weekday_of_month(year, 1, 0, 3), 'Martin Luther King Jr. Day'),
        (_nth_weekday_of_month(year, 2, 0, 3), 'Presidents Day'),
        (_last_weekday_of_month(year, 5, 0), 'Memorial Day'),
        (_observed_holiday(year, 6, 19), 'Juneteenth'),
        (_observed_holiday(year, 7, 4), 'Independence Day'),
        (_nth_weekday_of_month(year, 9, 0, 1), 'Labor Day'),
        (_nth_weekday_of_month(year, 10, 0, 2), 'Columbus Day'),
        (_observed_holiday(year, 11, 11), 'Veterans Day'),
        (_nth_weekday_of_month(year, 11, 3, 4), 'Thanksgiving Day'),
        (_observed_holiday(year, 12, 25), 'Christmas Day'),
    ]
    return [
        _calendar_event(day_value, title, 'Federal holiday', tone='holiday', source='holiday')
        for day_value, title in holidays
    ]


def irs_calendar_events(year: int):
    events = [
        _calendar_event(date(year, 1, 15), 'Estimated tax payment due', 'Quarter 4 prior-year estimate due', tone='irs', source='irs'),
        _calendar_event(date(year, 1, 31), 'W-2 / 1099 deadline', 'File and furnish W-2s and most 1099s', tone='irs', source='irs'),
        _calendar_event(date(year, 1, 31), 'Form 941 due', 'Quarter 4 Form 941 due', tone='irs', source='irs'),
        _calendar_event(date(year, 4, 15), 'Federal tax deadline', 'Individual federal return and Q1 estimated tax due', tone='irs', source='irs'),
        _calendar_event(date(year, 4, 30), 'Form 941 due', 'Quarter 1 Form 941 due', tone='irs', source='irs'),
        _calendar_event(date(year, 6, 15), 'Estimated tax payment due', 'Quarter 2 estimate due', tone='irs', source='irs'),
        _calendar_event(date(year, 7, 31), 'Form 941 due', 'Quarter 2 Form 941 due', tone='irs', source='irs'),
        _calendar_event(date(year, 9, 15), 'Estimated tax payment due', 'Quarter 3 estimate due', tone='irs', source='irs'),
        _calendar_event(date(year, 10, 31), 'Form 941 due', 'Quarter 3 Form 941 due', tone='irs', source='irs'),
    ]
    for month in range(1, 13):
        events.append(
            _calendar_event(
                date(year, month, 15),
                'EFTPS payment reminder',
                'Review payroll tax deposit timing and confirm any EFTPS payment due dates.',
                tone='payment',
                source='payment',
            )
        )
    return events


def client_billing_calendar_events(client_id: int, client_row, year: int):
    events = []
    next_billing = (client_row['subscription_next_billing_date'] or '').strip() if client_row else ''
    if next_billing and next_billing.startswith(f'{year:04d}-'):
        try:
            billing_date = date.fromisoformat(next_billing)
        except ValueError:
            billing_date = None
        if billing_date:
            events.append(
                _calendar_event(
                    billing_date,
                    'Subscription billing date',
                    f"{client_row['subscription_plan_code'] or 'Subscription'} renewal target date",
                    tone='payment',
                    source='subscription',
                )
            )
    with get_conn() as conn:
        fee_rows = conn.execute(
            """SELECT description, due_date, amount_due
               FROM business_payment_items
               WHERE client_id=?
                 AND COALESCE(status,'pending') IN ('pending','processing')
                 AND COALESCE(archived_at,'')=''
                 AND COALESCE(due_date,'')<>''""",
            (client_id,),
        ).fetchall()
    for row in fee_rows:
        due_date = (row['due_date'] or '').strip()
        if due_date.startswith(f'{year:04d}-'):
            try:
                due_value = date.fromisoformat(due_date)
            except ValueError:
                due_value = None
            if due_value:
                events.append(
                    _calendar_event(
                        due_value,
                        'Administrator fee due',
                        f"{row['description']} · ${float(row['amount_due'] or 0):.2f}",
                        tone='payment',
                        source='admin_fee',
                    )
                )
    return events


def calendar_events_by_day(events):
    out = {}
    for item in events:
        out.setdefault(item['event_date'], []).append(item)
    return out


def calendar_events_in_month(events, month_start: date, month_end: date):
    return [
        item for item in events
        if month_start.isoformat() <= item['event_date'] <= month_end.isoformat()
    ]


def upcoming_calendar_events(events, today_value: date, limit: int = 14):
    upcoming = [item for item in events if item['event_date'] >= today_value.isoformat()]
    upcoming.sort(key=lambda item: (item['event_date'], item['title']))
    return upcoming[:limit]


@app.route('/admin-calendar', methods=['GET', 'POST'])
@admin_required
def admin_calendar():
    user = current_user()
    from datetime import date
    import calendar as pycal

    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    today = date.today()
    if not year or not month:
        year, month = today.year, today.month

    if request.method == 'POST':
        reminder_type = request.form.get('reminder_type', '').strip()
        reminder_date = request.form.get('reminder_date', '').strip()
        note = request.form.get('note', '').strip()
        if reminder_type and reminder_date:
            with get_conn() as conn:
                conn.execute(
                    'INSERT INTO admin_calendar_reminders (admin_user_id, reminder_type, reminder_date, note) VALUES (?,?,?,?)',
                    (user['id'], reminder_type, reminder_date, note)
                )
                conn.commit()
            flash('Reminder added.', 'success')
        else:
            flash('Select a reminder type and date.', 'error')
        return redirect(url_for('admin_calendar', year=year, month=month))

    month_start = date(year, month, 1)
    last_day = pycal.monthrange(year, month)[1]
    month_end = date(year, month, last_day)

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM admin_calendar_reminders WHERE admin_user_id=? AND reminder_date>=? AND reminder_date<=? ORDER BY reminder_date ASC, id ASC",
            (user['id'], month_start.isoformat(), month_end.isoformat())
        ).fetchall()
        upcoming = conn.execute(
            "SELECT * FROM admin_calendar_reminders WHERE admin_user_id=? AND reminder_date>=? ORDER BY reminder_date ASC, id ASC LIMIT 12",
            (user['id'], today.isoformat())
        ).fetchall()

    system_events = national_holiday_events(year) + irs_calendar_events(year)
    reminders_by_day = {}
    for r in rows:
        reminders_by_day.setdefault(r['reminder_date'], []).append(r)
    system_events_by_day = calendar_events_by_day(calendar_events_in_month(system_events, month_start, month_end))

    cal = pycal.Calendar(firstweekday=0)
    weeks = list(cal.monthdatescalendar(year, month))

    prev_month = month - 1
    prev_year = year
    if prev_month == 0:
        prev_month = 12
        prev_year -= 1
    next_month = month + 1
    next_year = year
    if next_month == 13:
        next_month = 1
        next_year += 1

    return render_template(
        'admin_calendar.html',
        year=year,
        month=month,
        month_name=pycal.month_name[month],
        weeks=weeks,
        reminders_by_day=reminders_by_day,
        system_events_by_day=system_events_by_day,
        reminder_types=reminder_types(),
        upcoming=upcoming,
        upcoming_system=upcoming_calendar_events(system_events, today, limit=14),
        today=today.isoformat(),
        prev_year=prev_year,
        prev_month=prev_month,
        next_year=next_year,
        next_month=next_month,
    )



def business_reminder_types():
    return [
        'Payroll day',
        'Invoice follow-up',
        'Insurance renewal',
        'License renewal',
        'Annual report',
        'Tax payment reminder',
        'Material pickup',
        'Custom reminder',
    ]


def income_category_options():
    return [
        ('service_income', 'Service Income'),
        ('product_sale', 'Product / Sales Income'),
        ('other_income', 'Other Income'),
    ]


def income_category_label_map():
    return dict(income_category_options())


def invoice_status_options():
    return [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('viewed', 'Viewed'),
        ('partial', 'Partial Payment'),
        ('overdue', 'Overdue'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ]


def invoice_status_label_map():
    return dict(invoice_status_options())


def estimate_status_options():
    return [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('viewed', 'Viewed'),
        ('approved', 'Approved'),
        ('declined', 'Declined'),
        ('converted', 'Converted to Invoice'),
        ('expired', 'Expired'),
    ]


def estimate_status_label_map():
    return dict(estimate_status_options())


def normalize_estimate_status(value: str, *, default: str = 'draft') -> str:
    allowed = {key for key, _ in estimate_status_options()}
    cleaned = (value or '').strip().lower()
    return cleaned if cleaned in allowed else default


def estimate_current_status(row) -> str:
    base_status = normalize_estimate_status(row['invoice_status'] or '', default='draft')
    if base_status in {'approved', 'declined', 'converted'}:
        return base_status
    expiration_date = (row['estimate_expiration_date'] or '').strip()
    if expiration_date and expiration_date < date.today().isoformat():
        return 'expired'
    return base_status


def normalize_invoice_status(value: str, *, default: str = 'draft') -> str:
    allowed = {key for key, _ in invoice_status_options()}
    cleaned = (value or '').strip().lower()
    return cleaned if cleaned in allowed else default


def invoice_payment_progress_status(row) -> str:
    total_amount = money(row['invoice_total_amount'] or 0)
    paid_amount = money(row['paid_amount'] or 0)
    if total_amount > 0 and paid_amount >= total_amount:
        return 'paid'
    if paid_amount > 0 and paid_amount < max(total_amount, 0.01):
        return 'partial'
    base_status = normalize_invoice_status(row['invoice_status'] or '', default='draft')
    if (
        base_status in {'sent', 'viewed', 'partial', 'overdue'}
        and (row['due_date'] or '').strip()
        and (row['due_date'] or '') < date.today().isoformat()
        and paid_amount < total_amount
    ):
        return 'overdue'
    return base_status


def invoice_balance_due(row) -> float:
    total_amount = money(row['invoice_total_amount'] or 0)
    paid_amount = money(row['paid_amount'] or 0)
    return money(max(total_amount - paid_amount, 0))


def generate_invoice_public_token() -> str:
    return secrets.token_urlsafe(24)


def ensure_invoice_public_token(conn: sqlite3.Connection, invoice_id: int) -> str:
    row = conn.execute('SELECT public_invoice_token FROM invoices WHERE id=?', (invoice_id,)).fetchone()
    existing = (row['public_invoice_token'] or '').strip() if row else ''
    if existing:
        return existing
    while True:
        token = generate_invoice_public_token()
        taken = conn.execute('SELECT 1 FROM invoices WHERE public_invoice_token=? LIMIT 1', (token,)).fetchone()
        if not taken:
            conn.execute('UPDATE invoices SET public_invoice_token=? WHERE id=?', (token, invoice_id))
            return token


def public_invoice_url(token: str) -> str:
    return public_app_url(f'/customer-invoice/{token}')


def public_invoice_payment_url(token: str) -> str:
    return public_app_url(f'/customer-invoice/{token}/pay')


def public_estimate_url(token: str) -> str:
    return public_app_url(f'/customer-estimate/{token}')


def invoice_line_items_for_ids(conn: sqlite3.Connection, invoice_ids) -> dict[int, list[sqlite3.Row]]:
    ids = [int(invoice_id) for invoice_id in invoice_ids or [] if invoice_id]
    if not ids:
        return {}
    placeholders = ','.join('?' for _ in ids)
    rows = conn.execute(
        f'''SELECT *
            FROM invoice_line_items
            WHERE invoice_id IN ({placeholders})
            ORDER BY invoice_id, sort_order, id''',
        tuple(ids),
    ).fetchall()
    grouped: dict[int, list[sqlite3.Row]] = {}
    for row in rows:
        grouped.setdefault(int(row['invoice_id']), []).append(row)
    return grouped


def parse_invoice_line_items(form) -> tuple[list[dict], list[str]]:
    descriptions = form.getlist('line_description')
    quantities = form.getlist('line_quantity')
    unit_prices = form.getlist('line_unit_price')
    max_rows = max(len(descriptions), len(quantities), len(unit_prices), 0)
    items: list[dict] = []
    errors: list[str] = []
    for idx in range(max_rows):
        description = (descriptions[idx] if idx < len(descriptions) else '').strip()
        quantity_text = (quantities[idx] if idx < len(quantities) else '').strip()
        unit_price_text = (unit_prices[idx] if idx < len(unit_prices) else '').strip()
        if not any([description, quantity_text, unit_price_text]):
            continue
        if not description:
            errors.append(f'Line item {idx + 1} needs a description.')
            continue
        try:
            quantity = Decimal(quantity_text or '1')
        except Exception:
            errors.append(f'Line item {idx + 1} has an invalid quantity.')
            continue
        if quantity <= 0:
            errors.append(f'Line item {idx + 1} must use a quantity above zero.')
            continue
        unit_price = normalize_money_amount(unit_price_text or '0')
        if unit_price is None or unit_price < 0:
            errors.append(f'Line item {idx + 1} has an invalid unit price.')
            continue
        line_total = (quantity * unit_price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        items.append({
            'sort_order': idx,
            'description': description[:200],
            'quantity': float(quantity),
            'quantity_display': f'{quantity.normalize()}' if quantity != quantity.to_integral() else str(int(quantity)),
            'unit_price': float(unit_price),
            'line_total': float(line_total),
        })
    if not items:
        errors.append('Add at least one invoice line item before saving a customer invoice.')
    return items, errors


def invoice_subtotal(items: list[dict]) -> Decimal:
    return sum((Decimal(str(item['line_total'])) for item in items), Decimal('0.00')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def convert_estimate_to_invoice_document(conn: sqlite3.Connection, estimate_row, line_items: list[sqlite3.Row], *, actor_user_id=None) -> int:
    next_job = conn.execute('SELECT COALESCE(MAX(job_number),0)+1 n FROM invoices WHERE client_id=?', (estimate_row['client_id'],)).fetchone()['n']
    token = generate_invoice_public_token()
    while conn.execute('SELECT 1 FROM invoices WHERE public_invoice_token=? LIMIT 1', (token,)).fetchone():
        token = generate_invoice_public_token()
    due_date = (date.today() + timedelta(days=14)).isoformat()
    cursor = conn.execute(
        '''INSERT INTO invoices (
            client_id, customer_contact_id, job_number, record_kind, invoice_title, client_name, recipient_email, client_address,
            invoice_total_amount, paid_amount, invoice_date, due_date, estimate_expiration_date, invoice_status,
            public_invoice_token, public_payment_link, sent_at, last_reminder_at, reminder_count,
            customer_viewed_at, customer_paid_at, approved_at, declined_at, converted_invoice_id,
            payment_note, notes, income_category, sales_tax_amount, sales_tax_paid
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (
            estimate_row['client_id'],
            estimate_row['customer_contact_id'] if 'customer_contact_id' in estimate_row.keys() else None,
            next_job,
            'customer_invoice',
            estimate_row['invoice_title'] or 'Customer Invoice',
            estimate_row['client_name'],
            estimate_row['recipient_email'],
            estimate_row['client_address'],
            estimate_row['invoice_total_amount'] or 0,
            0,
            date.today().isoformat(),
            due_date,
            '',
            'draft',
            token,
            estimate_row['public_payment_link'] or '',
            '',
            '',
            0,
            '',
            '',
            '',
            '',
            None,
            '',
            estimate_row['notes'] or '',
            'service_income',
            estimate_row['sales_tax_amount'] or 0,
            0,
        )
    )
    invoice_id = cursor.lastrowid
    for item in line_items:
        conn.execute(
            '''INSERT INTO invoice_line_items (invoice_id, sort_order, description, quantity, unit_price, line_total)
               VALUES (?,?,?,?,?,?)''',
            (
                invoice_id,
                item['sort_order'],
                item['description'],
                item['quantity'],
                item['unit_price'],
                item['line_total'],
            )
        )
    conn.execute(
        '''UPDATE invoices
           SET invoice_status='converted', converted_invoice_id=?, payment_note=?, approved_at=CASE WHEN COALESCE(approved_at,'')='' THEN ? ELSE approved_at END
           WHERE id=?''',
        (
            invoice_id,
            'Converted into a final invoice.',
            now_iso(),
            estimate_row['id'],
        )
    )
    return invoice_id


def automatic_invoice_reminders(conn: sqlite3.Connection, *, client_id: int, created_by_user_id=None) -> int:
    if not smtp_email_ready():
        return 0
    today_iso = date.today().isoformat()
    reminder_cutoff = (datetime.now() - timedelta(days=3)).isoformat(timespec='seconds')
    rows = conn.execute(
        '''SELECT i.*, c.business_name
           FROM invoices i
           JOIN clients c ON c.id = i.client_id
           WHERE i.client_id=?
             AND COALESCE(i.record_kind,'income_record')='customer_invoice'
             AND COALESCE(i.recipient_email,'')<>''
             AND COALESCE(i.invoice_status,'draft') IN ('sent','viewed','partial','overdue')
             AND COALESCE(i.invoice_total_amount,0) > COALESCE(i.paid_amount,0)
             AND COALESCE(i.due_date,'')<>''
             AND i.due_date <= ?
             AND (COALESCE(i.last_reminder_at,'')='' OR i.last_reminder_at <= ?)
           ORDER BY i.due_date, i.id
           LIMIT 5''',
        (client_id, today_iso, reminder_cutoff),
    ).fetchall()
    sent_count = 0
    for row in rows:
        token = ensure_invoice_public_token(conn, row['id'])
        view_link = public_invoice_url(token)
        pay_link = (row['public_payment_link'] or '').strip()
        try:
            email_result = send_customer_invoice_reminder_email(
                to_email=row['recipient_email'],
                to_name=row['client_name'],
                business_name=row['business_name'],
                invoice_number=row['job_number'] or row['id'],
                invoice_title=row['invoice_title'] or 'Customer Invoice',
                invoice_link=view_link,
                due_date=row['due_date'] or '',
                balance_due=invoice_balance_due(row),
                payment_link=pay_link,
            )
            conn.execute(
                '''UPDATE invoices
                   SET invoice_status='overdue', last_reminder_at=?, reminder_count=COALESCE(reminder_count,0)+1
                   WHERE id=?''',
                (now_iso(), row['id']),
            )
            log_email_delivery(
                client_id=client_id,
                email_type=email_result['email_type'],
                recipient_email=row['recipient_email'],
                recipient_name=row['client_name'],
                subject=email_result['subject'],
                body_text=email_result['body_text'],
                body_html=email_result['body_html'],
                status='sent',
                created_by_user_id=created_by_user_id,
            )
            sent_count += 1
        except Exception as exc:
            log_email_delivery(
                client_id=client_id,
                email_type='customer_invoice_reminder',
                recipient_email=row['recipient_email'],
                recipient_name=row['client_name'],
                subject=f'Invoice reminder #{row["job_number"] or row["id"]}',
                status='failed',
                error_message=str(exc)[:500],
                created_by_user_id=created_by_user_id,
            )
    return sent_count


def admin_todo_priorities():
    return ['low', 'medium', 'high']


def business_help_request_types():
    return [
        'Suggestion',
        'Feature request',
        'Usability feedback',
        'Support request',
        'Improvement idea',
    ]


def welcome_center_video_topics():
    return [
        {
            'title': 'Start Here',
            'length': '45 to 75 seconds',
            'description': 'A first-step walkthrough for the business owner showing how to settle in, review the workspace, and understand the layout.',
        },
        {
            'title': 'Billing and Subscription Setup',
            'length': '30 to 60 seconds',
            'description': 'A clear explanation of subscription billing, payment methods on file, and how the business should manage administrator fees.',
        },
        {
            'title': 'Income Records and Tax Preparation Flow',
            'length': '45 to 90 seconds',
            'description': 'A practical guide showing how income records, expenses, payroll context, and tax-prep organization work together.',
        },
        {
            'title': 'Team Members and Payroll Context',
            'length': '45 to 90 seconds',
            'description': 'A guided explanation of team member setup, payouts, pay stubs, notices, and how the team portal fits into the business workflow.',
        },
    ]


def business_benefits_opportunities():
    return [
        {
            'title': 'Health coverage and small-business tax credit',
            'eyebrow': 'Possible tax advantage',
            'summary': 'If you offer qualifying health coverage, some smaller employers may be able to claim a federal tax credit.',
            'bullets': [
                'The IRS says the maximum credit is 50% of premiums paid for eligible small business employers and 35% for eligible small tax-exempt employers.',
                'The credit is generally tied to very small employers, average wage limits, and premium contributions.',
                'SHOP enrollment is generally the path eligible small employers use to access this credit.',
            ],
            'links': [
                {'label': 'IRS: Small Business Health Care Tax Credit', 'url': 'https://www.irs.gov/affordable-care-act/employers/small-business-health-care-tax-credit-and-the-shop-marketplace'},
                {'label': 'HealthCare.gov: SHOP Overview', 'url': 'https://www.healthcare.gov/small-businesses/choose-and-enroll/shop-marketplace-overview/'},
            ],
        },
        {
            'title': 'Tax-favored medical benefit accounts',
            'eyebrow': 'Benefit design options',
            'summary': 'HSAs, FSAs, and HRAs can help structure employee health benefits in tax-advantaged ways when they are set up correctly.',
            'bullets': [
                'IRS Publication 969 explains that employer HSA contributions may be excluded from an employee\'s gross income.',
                'The same publication also outlines tax-favored rules for FSAs and HRAs, including employer contributions and reimbursement treatment.',
                'These accounts can improve benefit value without using the exact same design for every business.',
            ],
            'links': [
                {'label': 'IRS Publication 969: HSAs, FSAs, and HRAs', 'url': 'https://www.irs.gov/publications/p969'},
            ],
        },
        {
            'title': 'Retirement plan choices for smaller employers',
            'eyebrow': 'Owner and team retention',
            'summary': 'Retirement benefits can support retention, owner planning, and long-term business maturity.',
            'bullets': [
                'The Department of Labor provides small-business guidance covering 401(k), profit-sharing, SIMPLE IRA, SEP, and payroll-deduction IRA options.',
                'Different plans create different cost, matching, administration, and compliance responsibilities.',
                'The best option often depends on payroll size, owner goals, and how much flexibility you want year to year.',
            ],
            'links': [
                {'label': 'DOL: Choosing a Retirement Plan for Small Business', 'url': 'https://www.dol.gov/agencies/ebsa/employers-and-advisers/small-business-owners/choosing-a-plan'},
            ],
        },
        {
            'title': 'Fringe benefits and retirement education',
            'eyebrow': 'Tax treatment matters',
            'summary': 'Some fringe benefits and retirement planning support can receive favorable tax treatment when they are offered correctly.',
            'bullets': [
                'IRS Publication 15-B is the main federal guide for fringe benefit tax treatment.',
                'It also explains that retirement planning advice may be excluded from wages if you maintain a qualified retirement plan and follow the applicable rules.',
                'Benefit value is not just about what you offer; it is also about how it is taxed and reported.',
            ],
            'links': [
                {'label': 'IRS Publication 15-B: Fringe Benefits', 'url': 'https://www.irs.gov/publications/p15b'},
            ],
        },
    ]


def business_obligation_guides():
    return [
        {
            'title': 'Payroll withholding, reporting, and employer tax basics',
            'summary': 'Use the IRS employer guides as the baseline for withholding, deposits, wage reporting, and benefit-tax treatment.',
            'bullets': [
                'Publication 15 is the main employer guide for withholding and employment tax responsibilities.',
                'Publication 15-B supplements it for fringe benefits and their payroll-tax treatment.',
                'These are foundational references even if you use payroll software or outside payroll help.',
            ],
            'links': [
                {'label': 'IRS Publication 15: Employer\'s Tax Guide', 'url': 'https://www.irs.gov/publications/p15'},
                {'label': 'IRS Publication 15-B: Fringe Benefits', 'url': 'https://www.irs.gov/publications/p15b'},
            ],
        },
        {
            'title': 'Health coverage rules for larger employers',
            'summary': 'Affordable Care Act employer rules depend heavily on workforce size and coverage design.',
            'bullets': [
                'The IRS says applicable large employers are generally those averaging at least 50 full-time employees, including full-time-equivalent employees, in the prior year.',
                'If those rules apply, affordability, minimum value, and offer coverage thresholds can matter.',
                'This is one of the first size-based checkpoints to review before adding or changing health benefits.',
            ],
            'links': [
                {'label': 'IRS: Employer Shared Responsibility Provisions', 'url': 'https://www.irs.gov/affordable-care-act/employers/employer-shared-responsibility-provisions'},
                {'label': 'IRS ACA Employer Hub', 'url': 'https://www.irs.gov/affordable-care-act/employers'},
            ],
        },
        {
            'title': 'Posters, notices, and leave obligations',
            'summary': 'Notice and leave rules vary by statute, employer size, and workforce situation.',
            'bullets': [
                'The Department of Labor notes that posting requirements vary by statute and not every employer is covered by every posting rule.',
                'FMLA obligations are also coverage-based, so smaller businesses should check before assuming the law does or does not apply.',
                'This is one area where federal and state requirements can stack together.',
            ],
            'links': [
                {'label': 'DOL: Workplace Posters', 'url': 'https://www.dol.gov/general/topics/posters'},
                {'label': 'DOL: FMLA Employer Guide', 'url': 'https://www.dol.gov/agencies/whd/fmla/employer-guide'},
            ],
        },
        {
            'title': 'Benefit-plan administration and compliance',
            'summary': 'If you sponsor health or retirement plans, the plan itself creates ongoing compliance and administration responsibilities.',
            'bullets': [
                'EBSA provides plan-sponsor guidance for retirement plans, health plans, reporting, filings, and corrections.',
                'This is especially useful when your business is adding benefits for the first time or adjusting plan structure.',
                'Use these tools early so the benefit offering is built correctly instead of fixed later.',
            ],
            'links': [
                {'label': 'DOL EBSA: Employers and Advisers', 'url': 'https://www.dol.gov/agencies/ebsa/employers-and-advisers'},
                {'label': 'DOL elaws: Health Benefits Advisor', 'url': 'https://webapps.dol.gov/elaws/ebsa/health/index.htm'},
            ],
        },
    ]


def benefits_official_resource_links():
    return [
        {'label': 'IRS Publication 15', 'url': 'https://www.irs.gov/publications/p15', 'caption': 'Employer withholding, deposits, and reporting basics'},
        {'label': 'IRS Publication 15-B', 'url': 'https://www.irs.gov/publications/p15b', 'caption': 'Fringe benefit tax treatment'},
        {'label': 'IRS Publication 969', 'url': 'https://www.irs.gov/publications/p969', 'caption': 'HSAs, FSAs, HRAs, and tax-favored health plans'},
        {'label': 'IRS ACA Employer Hub', 'url': 'https://www.irs.gov/affordable-care-act/employers', 'caption': 'ACA employer resources and health coverage tax rules'},
        {'label': 'HealthCare.gov SHOP', 'url': 'https://www.healthcare.gov/small-businesses/choose-and-enroll/shop-marketplace-overview/', 'caption': 'Small-group coverage overview and enrollment paths'},
        {'label': 'DOL Workplace Posters', 'url': 'https://www.dol.gov/general/topics/posters', 'caption': 'Federal poster guidance and poster advisor access'},
        {'label': 'DOL FMLA Employer Guide', 'url': 'https://www.dol.gov/agencies/whd/fmla/employer-guide', 'caption': 'Employer leave guidance and administration help'},
        {'label': 'DOL EBSA Small Business Retirement Help', 'url': 'https://www.dol.gov/agencies/ebsa/employers-and-advisers/small-business-owners/choosing-a-plan', 'caption': 'Retirement plan choices for small employers'},
    ]


def other_expense_categories():
    return [
        'food',
        'fuel',
        'repair',
        'insurance',
        'phone / internet',
        'supplies',
        'equipment',
        'subcontractors',
        'advertising',
        'software',
        'other',
    ]


def business_payment_statuses():
    return ['pending', 'processing', 'paid', 'cancelled']


def business_payment_summary(client_id: int):
    with get_conn() as conn:
        active_rows = conn.execute(
            '''SELECT *
               FROM business_payment_items
               WHERE client_id=? AND COALESCE(archived_at,'')=''
               ORDER BY CASE COALESCE(status,'pending')
                          WHEN 'pending' THEN 0
                          WHEN 'processing' THEN 1
                          WHEN 'paid' THEN 2
                          WHEN 'cancelled' THEN 3
                          ELSE 4
                        END,
                        CASE WHEN COALESCE(due_date,'')='' THEN 1 ELSE 0 END,
                        due_date ASC, id DESC''',
            (client_id,)
        ).fetchall()
        archived_count = conn.execute(
            "SELECT COUNT(*) c FROM business_payment_items WHERE client_id=? AND COALESCE(archived_at,'')<>''",
            (client_id,)
        ).fetchone()['c']
    open_statuses = {'pending', 'processing'}
    amount_due_decimal = sum(
        (
            (normalize_money_amount(r['amount_due']) or Decimal('0.00'))
            for r in active_rows
            if (r['status'] or 'pending') in open_statuses
        ),
        Decimal('0.00')
    )
    paid_total_decimal = sum(
        (
            (normalize_money_amount(r['amount_due']) or Decimal('0.00'))
            for r in active_rows
            if (r['status'] or '') == 'paid'
        ),
        Decimal('0.00')
    )
    return {
        'rows': active_rows,
        'amount_due': float(amount_due_decimal.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
        'paid_total': float(paid_total_decimal.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
        'pending_count': sum(1 for r in active_rows if (r['status'] or 'pending') in open_statuses),
        'paid_count': sum(1 for r in active_rows if (r['status'] or '') == 'paid'),
        'cancelled_count': sum(1 for r in active_rows if (r['status'] or '') == 'cancelled'),
        'archived_count': archived_count,
    }


def all_business_payment_items():
    with get_conn() as conn:
        return conn.execute(
            '''SELECT bpi.*, c.business_name, u.full_name created_by_name
               FROM business_payment_items bpi
               JOIN clients c ON c.id=bpi.client_id
               LEFT JOIN users u ON u.id=bpi.created_by_user_id
               WHERE COALESCE(bpi.archived_at,'')=''
               ORDER BY CASE COALESCE(bpi.status,'pending')
                          WHEN 'pending' THEN 0
                          WHEN 'processing' THEN 1
                          WHEN 'paid' THEN 2
                          WHEN 'cancelled' THEN 3
                          ELSE 4
                        END,
                        CASE WHEN COALESCE(bpi.due_date,'')='' THEN 1 ELSE 0 END,
                        bpi.due_date ASC, bpi.id DESC'''
        ).fetchall()


@app.route('/admin-tasks', methods=['GET', 'POST'])
@admin_required
def admin_tasks():
    user = current_user()

    if request.method == 'POST':
        action = request.form.get('action', 'add').strip().lower()
        item_id = request.form.get('item_id', type=int)
        with get_conn() as conn:
            if action == 'add':
                title = request.form.get('title', '').strip()
                due_date = request.form.get('due_date', '').strip()
                priority = request.form.get('priority', 'medium').strip().lower()
                if priority not in admin_todo_priorities():
                    priority = 'medium'
                if title:
                    conn.execute(
                        'INSERT INTO admin_todo_items (admin_user_id, title, due_date, priority) VALUES (?,?,?,?)',
                        (user['id'], title, due_date, priority)
                    )
                    conn.commit()
                    flash('Task added.', 'success')
                else:
                    flash('Enter a title or short note.', 'error')
            elif action == 'toggle' and item_id:
                row = conn.execute('SELECT * FROM admin_todo_items WHERE id=? AND admin_user_id=?', (item_id, user['id'])).fetchone()
                if row:
                    next_value = 0 if int(row['is_completed'] or 0) else 1
                    completed_at = datetime.now().isoformat(timespec='seconds') if next_value else ''
                    conn.execute('UPDATE admin_todo_items SET is_completed=?, completed_at=? WHERE id=? AND admin_user_id=?', (next_value, completed_at, item_id, user['id']))
                    conn.commit()
                    flash('Task updated.', 'success')
            return redirect(url_for('admin_tasks'))

    with get_conn() as conn:
        todo_items = conn.execute(
            "SELECT * FROM admin_todo_items WHERE admin_user_id=? ORDER BY is_completed ASC, CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, CASE WHEN due_date='' THEN 1 ELSE 0 END, due_date ASC, id DESC",
            (user['id'],)
        ).fetchall()

    open_items = [row for row in todo_items if not int(row['is_completed'] or 0)]
    completed_items = [row for row in todo_items if int(row['is_completed'] or 0)]

    return render_template(
        'admin_tasks.html',
        todo_items=todo_items,
        open_items=open_items,
        completed_items=completed_items,
        priority_options=admin_todo_priorities(),
    )


@app.route('/business-calendar', methods=['GET', 'POST'])
@login_required
def business_calendar():
    user = current_user()
    if user['role'] == 'admin':
        abort(403)

    client_id = selected_client_id(user, 'post' if request.method == 'POST' else 'get')

    with get_conn() as conn:
        client = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
        ensure_recurring_schedule_entries(conn, client_id=client_id, actor_user_id=user['id'])
        conn.commit()


    from datetime import date
    import calendar as pycal

    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    today = date.today()
    if not year or not month:
        year, month = today.year, today.month

    if request.method == 'POST':
        reminder_type = request.form.get('reminder_type', '').strip()
        reminder_date = request.form.get('reminder_date', '').strip()
        note = request.form.get('note', '').strip()
        if reminder_type and reminder_date:
            with get_conn() as conn:
                conn.execute(
                    'INSERT INTO business_calendar_reminders (client_id, created_by_user_id, reminder_type, reminder_date, note) VALUES (?,?,?,?,?)',
                    (client_id, user['id'], reminder_type, reminder_date, note)
                )
                conn.commit()
            flash('Reminder added.', 'success')
        else:
            flash('Select a reminder type and date.', 'error')
        return redirect(url_for('business_calendar', year=year, month=month, client_id=client_id))

    month_start = date(year, month, 1)
    last_day = pycal.monthrange(year, month)[1]
    month_end = date(year, month, last_day)

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM business_calendar_reminders WHERE client_id=? AND reminder_date>=? AND reminder_date<=? ORDER BY reminder_date ASC, id ASC",
            (client_id, month_start.isoformat(), month_end.isoformat())
        ).fetchall()
        upcoming = conn.execute(
            "SELECT * FROM business_calendar_reminders WHERE client_id=? AND reminder_date>=? ORDER BY reminder_date ASC, id ASC LIMIT 12",
            (client_id, today.isoformat())
        ).fetchall()
        schedule_rows = conn.execute(
            '''SELECT ws.*
               FROM work_schedule_entries ws
               WHERE ws.client_id=?
                 AND ws.schedule_date>=?
                 AND ws.schedule_date<=?
               ORDER BY ws.schedule_date ASC,
                        CASE WHEN COALESCE(ws.start_time,'')='' THEN 1 ELSE 0 END,
                        ws.start_time ASC,
                        ws.id ASC''',
            (client_id, month_start.isoformat(), month_end.isoformat())
        ).fetchall()
        upcoming_schedule = conn.execute(
            '''SELECT ws.*
               FROM work_schedule_entries ws
               WHERE ws.client_id=?
                 AND ws.schedule_date>=?
               ORDER BY ws.schedule_date ASC,
                        CASE WHEN COALESCE(ws.start_time,'')='' THEN 1 ELSE 0 END,
                        ws.start_time ASC,
                        ws.id ASC
                LIMIT 12''',
            (client_id, today.isoformat())
        ).fetchall()

    system_events = national_holiday_events(year) + irs_calendar_events(year) + client_billing_calendar_events(client_id, client, year)
    reminders_by_day = {}
    for r in rows:
        reminders_by_day.setdefault(r['reminder_date'], []).append(r)

    schedule_by_day = {}
    for row in schedule_rows:
        schedule_by_day.setdefault(row['schedule_date'], []).append(row)
    system_events_by_day = calendar_events_by_day(calendar_events_in_month(system_events, month_start, month_end))

    cal = pycal.Calendar(firstweekday=0)
    weeks = list(cal.monthdatescalendar(year, month))

    prev_month = month - 1
    prev_year = year
    if prev_month == 0:
        prev_month = 12
        prev_year -= 1
    next_month = month + 1
    next_year = year
    if next_month == 13:
        next_month = 1
        next_year += 1

    return render_template(
        'business_calendar.html',
        year=year,
        month=month,
        month_name=pycal.month_name[month],
        weeks=weeks,
        reminders_by_day=reminders_by_day,
        schedule_by_day=schedule_by_day,
        system_events_by_day=system_events_by_day,
        reminder_types=business_reminder_types(),
        upcoming=upcoming,
        upcoming_schedule=upcoming_schedule,
        upcoming_system=upcoming_calendar_events(system_events, today, limit=14),
        today=today.isoformat(),
        prev_year=prev_year,
        prev_month=prev_month,
        next_year=next_year,
        next_month=next_month,
        client_id=client_id,
        client=client,
    )


@app.route('/business-payments', methods=['GET', 'POST'])
@login_required
def business_payments_page():
    user = current_user()
    client_id = selected_client_id(user, 'post' if request.method == 'POST' else 'get')
    if request.method == 'POST':
        action = request.form.get('action', '').strip().lower()
        if action in {'add_payment_method', 'update_payment_method', 'delete_payment_method', 'update_subscription_billing_preferences'} and not valid_payment_csrf(request.form.get('csrf_token', '')):
            flash('Your session expired. Refresh the page and try again.', 'error')
            return redirect(url_for('business_payments_page', client_id=client_id))
        with get_conn() as conn:
            if action == 'update_subscription_billing_preferences':
                client = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
                next_billing_raw = request.form.get('subscription_next_billing_date', '').strip()
                next_billing_date = client['subscription_next_billing_date'] or ''
                if next_billing_raw:
                    parsed_next = parse_date(next_billing_raw)
                    if not parsed_next:
                        flash('Enter a valid next billing date.', 'error')
                        return redirect(url_for('business_payments_page', client_id=client_id))
                    next_billing_date = parsed_next.isoformat()
                autopay_enabled = 1 if request.form.get('subscription_autopay_enabled') in {'1', 'on', 'true', 'yes'} else 0
                default_active = conn.execute(
                    '''SELECT 1
                       FROM business_payment_methods
                       WHERE client_id=? AND is_default=1 AND COALESCE(status,'active')='active'
                       LIMIT 1''',
                    (client_id,),
                ).fetchone()
                if autopay_enabled and not default_active:
                    flash('Add an active default card or ACH method before enabling automatic withdrawal.', 'error')
                    return redirect(url_for('business_payments_page', client_id=client_id))
                conn.execute(
                    '''UPDATE clients
                       SET subscription_autopay_enabled=?, subscription_next_billing_date=?, updated_at=?, updated_by_user_id=?
                       WHERE id=?''',
                    (
                        autopay_enabled,
                        next_billing_date,
                        datetime.now().isoformat(timespec='seconds'),
                        user['id'],
                        client_id,
                    )
                )
                conn.commit()
                flash('Subscription billing preferences updated.', 'success')
                return redirect(url_for('business_payments_page', client_id=client_id))
            elif action == 'add_payment_method':
                cleaned, errors = validate_payment_method_form(request.form)
                if not errors:
                    if cleaned['is_default']:
                        conn.execute('UPDATE business_payment_methods SET is_default=0 WHERE client_id=?', (client_id,))
                    if cleaned['is_backup']:
                        conn.execute('UPDATE business_payment_methods SET is_backup=0 WHERE client_id=?', (client_id,))
                    conn.execute(
                        '''INSERT INTO business_payment_methods (client_id, method_type, label, status, is_default, is_backup, holder_name, brand_name, account_last4, expiry_display, account_type, card_number_enc, routing_number_enc, account_number_enc, details_note, created_by_user_id, updated_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (
                            client_id,
                            cleaned['method_type'],
                            cleaned['label'],
                            cleaned['status'],
                            cleaned['is_default'],
                            cleaned['is_backup'],
                            cleaned['holder_name'],
                            cleaned['brand_name'],
                            cleaned['account_last4'],
                            cleaned['expiry_display'],
                            cleaned['account_type'],
                            cleaned['card_number_enc'],
                            cleaned['routing_number_enc'],
                            cleaned['account_number_enc'],
                            cleaned['details_note'],
                            user['id'],
                            datetime.now().isoformat(timespec='seconds'),
                        )
                    )
                    sync_client_payment_method_summary(conn, client_id)
                    conn.commit()
                    flash('Payment method saved.', 'success')
                else:
                    for error in errors:
                        flash(error, 'error')
                return redirect(url_for('business_payments_page', client_id=client_id))
            elif action == 'update_payment_method':
                method_id = request.form.get('payment_method_id', type=int)
                row = conn.execute('SELECT * FROM business_payment_methods WHERE id=? AND client_id=?', (method_id, client_id)).fetchone() if method_id else None
                if not row:
                    flash('Payment method not found.', 'error')
                    return redirect(url_for('business_payments_page', client_id=client_id))
                cleaned, errors = validate_payment_method_form(request.form, existing=row)
                if not errors:
                    if cleaned['is_default']:
                        conn.execute('UPDATE business_payment_methods SET is_default=0 WHERE client_id=?', (client_id,))
                    if cleaned['is_backup']:
                        conn.execute('UPDATE business_payment_methods SET is_backup=0 WHERE client_id=?', (client_id,))
                    conn.execute(
                        '''UPDATE business_payment_methods
                           SET method_type=?, label=?, status=?, is_default=?, is_backup=?, holder_name=?, brand_name=?, account_last4=?, expiry_display=?, account_type=?, card_number_enc=?, routing_number_enc=?, account_number_enc=?, details_note=?, updated_at=?
                           WHERE id=? AND client_id=?''',
                        (
                            cleaned['method_type'],
                            cleaned['label'],
                            cleaned['status'],
                            cleaned['is_default'],
                            cleaned['is_backup'],
                            cleaned['holder_name'],
                            cleaned['brand_name'],
                            cleaned['account_last4'],
                            cleaned['expiry_display'],
                            cleaned['account_type'],
                            cleaned['card_number_enc'],
                            cleaned['routing_number_enc'],
                            cleaned['account_number_enc'],
                            cleaned['details_note'],
                            datetime.now().isoformat(timespec='seconds'),
                            method_id,
                            client_id,
                        )
                    )
                    sync_client_payment_method_summary(conn, client_id)
                    conn.commit()
                    flash('Payment method updated.', 'success')
                else:
                    for error in errors:
                        flash(error, 'error')
                return redirect(url_for('business_payments_page', client_id=client_id))
            elif action == 'delete_payment_method':
                method_id = request.form.get('payment_method_id', type=int)
                deleted = conn.execute('DELETE FROM business_payment_methods WHERE id=? AND client_id=?', (method_id, client_id))
                if deleted.rowcount:
                    sync_client_payment_method_summary(conn, client_id)
                    conn.commit()
                    flash('Payment method removed.', 'success')
                else:
                    flash('Payment method not found.', 'error')
                return redirect(url_for('business_payments_page', client_id=client_id))
    summary = business_payment_summary(client_id)
    with get_conn() as conn:
        client = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
        payment_methods = conn.execute(
            '''SELECT *
               FROM business_payment_methods
               WHERE client_id=?
               ORDER BY is_default DESC, is_backup DESC, updated_at DESC, id DESC''',
            (client_id,)
        ).fetchall()
    open_admin_fee_rows = [row for row in summary['rows'] if (row['status'] or 'pending') in {'pending', 'processing'}]
    return render_template('business_payments.html', client=client, client_id=client_id, payment_rows=summary['rows'], payment_summary=summary, open_admin_fee_rows=open_admin_fee_rows, payment_methods=payment_methods, payment_method_summary=payment_method_summary(payment_methods), open_fee_guidance=open_fee_guidance(open_admin_fee_rows), fee_collection_guidance=fee_collection_guidance, collection_method_labels=collection_method_label_map(), payment_method_type_options=payment_method_type_options(), payment_method_status_options=payment_method_status_options(), payment_method_type_labels=payment_method_type_label_map(), payment_method_status_labels=payment_method_status_label_map(), subscription_status_labels=subscription_status_label_map(), payment_csrf_token=payment_csrf_token())


@app.route('/dashboard')
@login_required
def dashboard():
    user = current_user()
    client_id = selected_client_id(user, 'get')
    with get_conn() as conn:
        client = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
        if not client or not allowed_client(user, client_id):
            abort(403)
        worker_rows = conn.execute(
            'SELECT * FROM workers WHERE client_id=? ORDER BY CASE WHEN status="active" THEN 0 ELSE 1 END, name',
            (client_id,),
        ).fetchall()
        invoice_rows = conn.execute(
            "SELECT * FROM invoices WHERE client_id=? AND COALESCE(record_kind,'income_record')<>'estimate' ORDER BY invoice_date DESC, id DESC LIMIT 8",
            (client_id,),
        ).fetchall()
        payment_methods = conn.execute(
            '''SELECT *
               FROM business_payment_methods
               WHERE client_id=?
               ORDER BY is_default DESC, is_backup DESC, updated_at DESC, id DESC''',
            (client_id,),
        ).fetchall()
    admin_fee_summary = business_payment_summary(client_id)
    open_admin_fee_rows = [row for row in admin_fee_summary['rows'] if (row['status'] or 'pending') in {'pending', 'processing'}]
    return render_template(
        'dashboard.html',
        client=client,
        client_id=client_id,
        workers=worker_rows,
        invoices=invoice_rows,
        summary=client_summary(client_id),
        payment_method_summary=payment_method_summary(payment_methods),
        subscription_status_labels=subscription_status_label_map(),
        admin_fee_summary=admin_fee_summary,
        open_fee_guidance=open_fee_guidance(open_admin_fee_rows),
        review_request=latest_review_request(client_id),
    )


@app.route('/operations-overview')
@login_required
def ops_overview():
    user = current_user()
    client_id = selected_client_id(user, 'get')
    with get_conn() as conn:
        prepare_ops_workspace(conn, client_id)
        client = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
        if not client or not allowed_client(user, client_id):
            abort(403)
        worker_rows = ops_worker_rows(conn, client_id)
        dashboard_summary = ops_dashboard_summary(conn, client_id)
        service_types = ops_service_types(conn, client_id)
        templates = ops_job_templates(conn, client_id)
    mark_messages_read(client_id, user['id'])
    return render_template(
        'ops_dashboard.html',
        client=client,
        client_id=client_id,
        workers=worker_rows,
        service_types=service_types,
        templates=templates,
        ops=dashboard_summary,
        job_status_options=ops_job_status_options(),
        priority_options=ops_priority_options(),
        progress_status_options=ops_progress_status_options(),
        today_iso=date.today().isoformat(),
    )


@app.route('/jobs', methods=['GET', 'POST'])
@login_required
def ops_jobs():
    user = current_user()
    client_id = selected_client_id(user, 'post' if request.method == 'POST' else 'get')
    selected_job_id = request.values.get('job_id', type=int)
    if request.method == 'POST':
        action = (request.form.get('action') or 'create_job').strip()
        with get_conn() as conn:
            prepare_ops_workspace(conn, client_id)
            if action in {'create_job', 'update_job'}:
                existing = conn.execute('SELECT * FROM jobs WHERE id=? AND client_id=?', (request.form.get('job_id', type=int), client_id)).fetchone() if action == 'update_job' else None
                try:
                    selected_job_id = ops_save_job(conn, client_id=client_id, actor_user_id=user['id'], form=request.form, existing=existing)
                    conn.commit()
                    flash('Job saved.', 'success')
                except ValueError as exc:
                    conn.rollback()
                    flash(str(exc), 'error')
            elif action == 'duplicate_job':
                duplicated_id = ops_duplicate_job(conn, client_id=client_id, job_id=request.form.get('job_id', type=int) or 0, actor_user_id=user['id'])
                if duplicated_id:
                    conn.commit()
                    selected_job_id = duplicated_id
                    flash('Job duplicated.', 'success')
                else:
                    conn.rollback()
                    flash('Job could not be duplicated.', 'error')
            elif action == 'update_status':
                job_id = request.form.get('job_id', type=int) or 0
                job = conn.execute('SELECT * FROM jobs WHERE id=? AND client_id=?', (job_id, client_id)).fetchone()
                if job:
                    status = normalize_ops_job_status(request.form.get('status'), default=job['status'])
                    progress_status = normalize_ops_progress_status(request.form.get('field_progress_status'), default=job['field_progress_status'])
                    completion_notes = (request.form.get('completion_notes', '') or '').strip()
                    completed_at = now_iso() if status == 'completed' else (job['completed_at'] or '')
                    conn.execute(
                        '''UPDATE jobs
                           SET status=?, field_progress_status=?, completion_notes=?, completed_at=?, last_progress_at=?, updated_at=?, updated_by_user_id=?
                           WHERE id=?''',
                        (status, progress_status, completion_notes, completed_at if status == 'completed' else '', now_iso(), now_iso(), user['id'], job_id),
                    )
                    ops_log_activity(
                        conn,
                        client_id=client_id,
                        job_id=job_id,
                        actor_type='user',
                        actor_id=user['id'],
                        event_type='status_changed',
                        event_text=f"Updated workflow to {ops_label(status)} / {ops_label(progress_status)}.",
                    )
                    conn.commit()
                    selected_job_id = job_id
                    flash('Job status updated.', 'success')
                else:
                    flash('Job not found.', 'error')
            elif action == 'add_note':
                job_id = request.form.get('job_id', type=int) or 0
                note_body = (request.form.get('note_body', '') or '').strip()
                note_type = (request.form.get('note_type', '') or 'internal').strip()[:30]
                if not note_body:
                    flash('Enter a note before saving.', 'error')
                else:
                    conn.execute(
                        'INSERT INTO job_notes (job_id, client_id, note_type, body, created_by_user_id) VALUES (?,?,?,?,?)',
                        (job_id, client_id, note_type, note_body[:3000], user['id']),
                    )
                    ops_log_activity(
                        conn,
                        client_id=client_id,
                        job_id=job_id,
                        actor_type='user',
                        actor_id=user['id'],
                        event_type='note_added',
                        event_text=f"Added a {note_type.replace('_', ' ')} note.",
                    )
                    conn.commit()
                    selected_job_id = job_id
                    flash('Job note added.', 'success')
            return redirect(url_for('ops_jobs', client_id=client_id, job_id=selected_job_id))
    status_filter = (request.args.get('status') or '').strip()
    search = (request.args.get('search') or '').strip()
    worker_filter = request.args.get('worker_id', type=int)
    service_type_filter = request.args.get('service_type_id', type=int)
    with get_conn() as conn:
        prepare_ops_workspace(conn, client_id)
        client = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
        jobs = [dict(row) for row in ops_jobs_query(conn, client_id=client_id, status=status_filter, worker_id=worker_filter, service_type_id=service_type_filter, search=search)]
        workers = ops_worker_rows(conn, client_id)
        service_types = ops_service_types(conn, client_id)
        templates = ops_job_templates(conn, client_id)
        locations = conn.execute('SELECT * FROM service_locations WHERE client_id=? ORDER BY location_name, address_line1', (client_id,)).fetchall()
        selected_job_id = selected_job_id or (jobs[0]['id'] if jobs else None)
        selected_job_rows = ops_jobs_query(conn, client_id=client_id, job_id=selected_job_id) if selected_job_id else []
        selected_job = dict(selected_job_rows[0]) if selected_job_rows else None
        selected_job_notes = ops_job_notes_for_job(conn, selected_job_id) if selected_job_id else []
        selected_job_activity = ops_job_activity_for_job(conn, selected_job_id) if selected_job_id else []
        template_seed = conn.execute('SELECT * FROM job_templates WHERE id=? AND client_id=?', (request.args.get('template_id', type=int), client_id)).fetchone() if request.args.get('template_id', type=int) else None
    return render_template(
        'ops_jobs.html',
        client=client,
        client_id=client_id,
        jobs=jobs,
        workers=workers,
        service_types=service_types,
        templates=templates,
        locations=locations,
        selected_job=selected_job,
        selected_job_notes=selected_job_notes,
        selected_job_activity=selected_job_activity,
        template_seed=template_seed,
        filters={'status': status_filter, 'search': search, 'worker_id': worker_filter, 'service_type_id': service_type_filter},
        job_status_options=ops_job_status_options(),
        progress_status_options=ops_progress_status_options(),
        priority_options=ops_priority_options(),
        today_iso=date.today().isoformat(),
    )


@app.route('/dispatch', methods=['GET', 'POST'])
@login_required
def ops_dispatch():
    user = current_user()
    client_id = selected_client_id(user, 'post' if request.method == 'POST' else 'get')
    dispatch_date = (request.values.get('date') or date.today().isoformat()).strip()
    if request.method == 'POST':
        action = (request.form.get('action') or '').strip()
        with get_conn() as conn:
            prepare_ops_workspace(conn, client_id)
            job_id = request.form.get('job_id', type=int) or 0
            job = conn.execute('SELECT * FROM jobs WHERE id=? AND client_id=?', (job_id, client_id)).fetchone()
            if not job:
                flash('Job not found.', 'error')
                return redirect(url_for('ops_dispatch', client_id=client_id, date=dispatch_date))
            if action == 'dispatch_assign':
                worker_ids = normalize_worker_assignment_ids(request.form.getlist('assigned_worker_ids'))
                ops_sync_job_assignments(conn, client_id=client_id, job_id=job_id, worker_ids=worker_ids, actor_user_id=user['id'])
                dispatch_note = (request.form.get('dispatch_note', '') or '').strip()
                status = normalize_ops_job_status(request.form.get('status'), default='assigned' if worker_ids else job['status'])
                conn.execute(
                    'UPDATE jobs SET status=?, dispatch_notes=?, updated_at=?, updated_by_user_id=? WHERE id=?',
                    (status, dispatch_note or job['dispatch_notes'], now_iso(), user['id'], job_id),
                )
                ops_log_activity(
                    conn,
                    client_id=client_id,
                    job_id=job_id,
                    actor_type='user',
                    actor_id=user['id'],
                    event_type='dispatch_updated',
                    event_text='Updated crew dispatch details.',
                )
                conn.commit()
                flash('Dispatch updated.', 'success')
            elif action == 'dispatch_progress':
                status = normalize_ops_job_status(request.form.get('status'), default=job['status'])
                progress_status = normalize_ops_progress_status(request.form.get('field_progress_status'), default=job['field_progress_status'])
                dispatch_note = (request.form.get('dispatch_note', '') or '').strip()
                conn.execute(
                    '''UPDATE jobs
                       SET status=?, field_progress_status=?, dispatch_notes=?, last_progress_at=?, updated_at=?, updated_by_user_id=?
                       WHERE id=?''',
                    (status, progress_status, dispatch_note or job['dispatch_notes'], now_iso(), now_iso(), user['id'], job_id),
                )
                ops_log_activity(
                    conn,
                    client_id=client_id,
                    job_id=job_id,
                    actor_type='user',
                    actor_id=user['id'],
                    event_type='dispatch_progress',
                    event_text=f"Dispatch moved the job to {ops_label(status)} / {ops_label(progress_status)}.",
                )
                conn.commit()
                flash('Dispatch progress updated.', 'success')
        return redirect(url_for('ops_dispatch', client_id=client_id, date=dispatch_date))
    anchor_date = date.fromisoformat(dispatch_date) if re.match(r'^\d{4}-\d{2}-\d{2}$', dispatch_date) else date.today()
    week_end = anchor_date + timedelta(days=6)
    with get_conn() as conn:
        prepare_ops_workspace(conn, client_id)
        client = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
        workers = [dict(row) for row in ops_worker_rows(conn, client_id)]
        jobs = [dict(row) for row in ops_jobs_query(conn, client_id=client_id, date_from=anchor_date.isoformat(), date_to=week_end.isoformat())]
        conflicts = ops_conflicts(conn, client_id)
    today_jobs = [job for job in jobs if ops_schedule_date(job['scheduled_start']) == anchor_date.isoformat()]
    unassigned_jobs = [job for job in today_jobs if int(job.get('assigned_count') or 0) == 0]
    active_jobs = [job for job in today_jobs if job['status'] == 'in_progress']
    dispatch_board = []
    for worker in workers:
        worker_jobs = []
        for job in today_jobs:
            assigned_ids = normalize_worker_assignment_ids((job.get('assigned_worker_ids_csv') or '').split(','))
            if worker['id'] in assigned_ids:
                worker_jobs.append(job)
        if worker_jobs or worker['status'] == 'active':
            dispatch_board.append({'worker': worker, 'jobs': worker_jobs})
    return render_template(
        'ops_dispatch.html',
        client=client,
        client_id=client_id,
        workers=workers,
        jobs=jobs,
        today_jobs=today_jobs,
        unassigned_jobs=unassigned_jobs,
        active_jobs=active_jobs,
        dispatch_board=dispatch_board,
        conflicts=conflicts,
        dispatch_date=anchor_date.isoformat(),
        week_end=week_end.isoformat(),
        job_status_options=ops_job_status_options(),
        progress_status_options=ops_progress_status_options(),
    )


@app.route('/schedule', methods=['GET', 'POST'])
@login_required
def ops_schedule():
    user = current_user()
    client_id = selected_client_id(user, 'post' if request.method == 'POST' else 'get')
    view = (request.values.get('view') or 'week').strip().lower()
    if view not in {'day', 'week', 'month'}:
        view = 'week'
    date_value = (request.values.get('date') or date.today().isoformat()).strip()
    anchor_date = date.fromisoformat(date_value) if re.match(r'^\d{4}-\d{2}-\d{2}$', date_value) else date.today()
    if request.method == 'POST':
        action = (request.form.get('action') or '').strip()
        with get_conn() as conn:
            prepare_ops_workspace(conn, client_id)
            if action == 'quick_add_job':
                try:
                    job_id = ops_save_job(conn, client_id=client_id, actor_user_id=user['id'], form=request.form)
                    conn.commit()
                    flash('Job added to the schedule.', 'success')
                    return redirect(url_for('ops_schedule', client_id=client_id, view=view, date=anchor_date.isoformat(), job_id=job_id))
                except ValueError as exc:
                    conn.rollback()
                    flash(str(exc), 'error')
            elif action == 'move_job':
                job_id = request.form.get('job_id', type=int) or 0
                job = conn.execute('SELECT * FROM jobs WHERE id=? AND client_id=?', (job_id, client_id)).fetchone()
                if job:
                    move_date = (request.form.get('scheduled_date', '') or '').strip()
                    move_start = (request.form.get('start_time', '') or '').strip()
                    move_end = (request.form.get('end_time', '') or '').strip()
                    scheduled_start = ops_schedule_timestamp(move_date, move_start)
                    scheduled_end = ops_schedule_end(move_date, move_start, move_end, job['estimated_duration_minutes'] or 0)
                    conn.execute(
                        'UPDATE jobs SET scheduled_start=?, scheduled_end=?, updated_at=?, updated_by_user_id=? WHERE id=?',
                        (scheduled_start, scheduled_end, now_iso(), user['id'], job_id),
                    )
                    ops_log_activity(
                        conn,
                        client_id=client_id,
                        job_id=job_id,
                        actor_type='user',
                        actor_id=user['id'],
                        event_type='rescheduled',
                        event_text=f"Rescheduled the job to {move_date}.",
                    )
                    conn.commit()
                    flash('Job rescheduled.', 'success')
        return redirect(url_for('ops_schedule', client_id=client_id, view=view, date=anchor_date.isoformat()))
    if view == 'day':
        range_start = range_end = anchor_date
        prev_date = anchor_date - timedelta(days=1)
        next_date = anchor_date + timedelta(days=1)
    elif view == 'week':
        range_start = anchor_date - timedelta(days=anchor_date.weekday())
        range_end = range_start + timedelta(days=6)
        prev_date = range_start - timedelta(days=7)
        next_date = range_start + timedelta(days=7)
    else:
        import calendar as pycal
        range_start = anchor_date.replace(day=1)
        range_end = range_start.replace(day=pycal.monthrange(range_start.year, range_start.month)[1])
        prev_date = (range_start - timedelta(days=1)).replace(day=1)
        next_date = (range_end + timedelta(days=1)).replace(day=1)
    worker_filter = request.args.get('worker_id', type=int)
    status_filter = (request.args.get('status') or '').strip()
    service_type_filter = request.args.get('service_type_id', type=int)
    with get_conn() as conn:
        prepare_ops_workspace(conn, client_id)
        client = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
        workers = ops_worker_rows(conn, client_id)
        service_types = ops_service_types(conn, client_id)
        jobs = [dict(row) for row in ops_jobs_query(conn, client_id=client_id, worker_id=worker_filter, status=status_filter, service_type_id=service_type_filter, date_from=range_start.isoformat(), date_to=range_end.isoformat())]
    jobs_by_day = {}
    for job in jobs:
        jobs_by_day.setdefault(ops_schedule_date(job['scheduled_start']), []).append(job)
    month_weeks = []
    month_name = ''
    if view == 'month':
        import calendar as pycal
        cal = pycal.Calendar(firstweekday=0)
        month_weeks = list(cal.monthdatescalendar(range_start.year, range_start.month))
        month_name = pycal.month_name[range_start.month]
    visible_days = [range_start + timedelta(days=offset) for offset in range((range_end - range_start).days + 1)]
    return render_template(
        'ops_schedule.html',
        client=client,
        client_id=client_id,
        workers=workers,
        service_types=service_types,
        jobs=jobs,
        jobs_by_day=jobs_by_day,
        view=view,
        anchor_date=anchor_date.isoformat(),
        range_start=range_start.isoformat(),
        range_end=range_end.isoformat(),
        prev_date=prev_date.isoformat(),
        next_date=next_date.isoformat(),
        visible_days=visible_days,
        month_weeks=month_weeks,
        month_name=month_name,
        filters={'worker_id': worker_filter, 'status': status_filter, 'service_type_id': service_type_filter},
        job_status_options=ops_job_status_options(),
        priority_options=ops_priority_options(),
        today_iso=date.today().isoformat(),
    )


@app.route('/team', methods=['GET', 'POST'])
@login_required
def ops_team():
    user = current_user()
    client_id = selected_client_id(user, 'post' if request.method == 'POST' else 'get')
    selected_worker_id = request.values.get('worker_id', type=int)
    if request.method == 'POST':
        action = (request.form.get('action') or '').strip()
        with get_conn() as conn:
            prepare_ops_workspace(conn, client_id)
            if action in {'create_worker', 'update_worker'}:
                existing = conn.execute('SELECT * FROM workers WHERE id=? AND client_id=?', (request.form.get('worker_id', type=int), client_id)).fetchone() if action == 'update_worker' else None
                try:
                    selected_worker_id = ops_save_worker_profile(conn, client_id=client_id, actor_user_id=user['id'], form=request.form, existing=existing)
                    conn.commit()
                    flash('Team member saved.', 'success')
                except ValueError as exc:
                    conn.rollback()
                    flash(str(exc), 'error')
        return redirect(url_for('ops_team', client_id=client_id, worker_id=selected_worker_id))
    with get_conn() as conn:
        prepare_ops_workspace(conn, client_id)
        client = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
        workers = [dict(row) for row in ops_worker_rows(conn, client_id)]
        selected_worker_id = selected_worker_id or (workers[0]['id'] if workers else None)
        selected_worker = next((row for row in workers if row['id'] == selected_worker_id), None)
        worker_jobs = [dict(row) for row in ops_jobs_query(conn, client_id=client_id, worker_id=selected_worker_id)] if selected_worker_id else []
        worker_availability = [row for row in ops_availability_rows(conn, client_id, date.today().isoformat(), (date.today() + timedelta(days=21)).isoformat()) if row['worker_id'] == selected_worker_id]
    return render_template(
        'ops_team.html',
        client=client,
        client_id=client_id,
        workers=workers,
        selected_worker=selected_worker,
        worker_jobs=worker_jobs,
        worker_availability=worker_availability,
        today_iso=date.today().isoformat(),
    )


@app.route('/availability', methods=['GET', 'POST'])
@login_required
def ops_availability():
    user = current_user()
    client_id = selected_client_id(user, 'post' if request.method == 'POST' else 'get')
    selected_worker_id = request.values.get('worker_id', type=int)
    if request.method == 'POST':
        action = (request.form.get('action') or 'save_availability').strip()
        with get_conn() as conn:
            prepare_ops_workspace(conn, client_id)
            if action == 'save_availability':
                availability_id = request.form.get('availability_id', type=int)
                worker_id = request.form.get('worker_id', type=int)
                available_date = (request.form.get('available_date', '') or '').strip()
                if not worker_id or not available_date:
                    flash('Worker and date are required.', 'error')
                else:
                    payload = (
                        normalize_ops_availability_status(request.form.get('availability_status')),
                        (request.form.get('start_time', '') or '').strip(),
                        (request.form.get('end_time', '') or '').strip(),
                        (request.form.get('note', '') or '').strip(),
                        now_iso(),
                        user['id'],
                    )
                    if availability_id:
                        conn.execute(
                            '''UPDATE worker_availability
                               SET availability_status=?, start_time=?, end_time=?, note=?, updated_at=?, created_by_user_id=?
                               WHERE id=? AND client_id=?''',
                            payload + (availability_id, client_id),
                        )
                    else:
                        conn.execute(
                            '''INSERT INTO worker_availability (
                                   worker_id, client_id, available_date, availability_status, start_time, end_time, note, created_by_user_id, updated_at
                               ) VALUES (?,?,?,?,?,?,?,?,?)''',
                            (worker_id, client_id, available_date, payload[0], payload[1], payload[2], payload[3], user['id'], now_iso()),
                        )
                    conn.commit()
                    flash('Availability saved.', 'success')
                    selected_worker_id = worker_id
            elif action == 'delete_availability':
                availability_id = request.form.get('availability_id', type=int)
                conn.execute('DELETE FROM worker_availability WHERE id=? AND client_id=?', (availability_id, client_id))
                conn.commit()
                flash('Availability block removed.', 'success')
        return redirect(url_for('ops_availability', client_id=client_id, worker_id=selected_worker_id))
    start_date = request.args.get('start_date', date.today().isoformat())
    end_date = request.args.get('end_date', (date.today() + timedelta(days=21)).isoformat())
    with get_conn() as conn:
        prepare_ops_workspace(conn, client_id)
        client = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
        workers = [dict(row) for row in ops_worker_rows(conn, client_id)]
        selected_worker_id = selected_worker_id or (workers[0]['id'] if workers else None)
        availability_rows = ops_availability_rows(conn, client_id, start_date, end_date)
        time_off_rows = conn.execute(
            '''SELECT tor.*, w.name AS worker_name
               FROM worker_time_off_requests tor
               JOIN workers w ON w.id = tor.worker_id
               WHERE w.client_id=?
               ORDER BY tor.start_date, tor.end_date''',
            (client_id,),
        ).fetchall()
        conflicts = ops_conflicts(conn, client_id)
    return render_template(
        'ops_availability.html',
        client=client,
        client_id=client_id,
        workers=workers,
        selected_worker_id=selected_worker_id,
        availability_rows=availability_rows,
        time_off_rows=time_off_rows,
        conflicts=conflicts,
        availability_status_options=ops_availability_status_options(),
        start_date=start_date,
        end_date=end_date,
        today_iso=date.today().isoformat(),
    )


@app.route('/activity')
@login_required
def ops_activity():
    user = current_user()
    client_id = selected_client_id(user, 'get')
    search = (request.args.get('search') or '').strip()
    with get_conn() as conn:
        prepare_ops_workspace(conn, client_id)
        client = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
        activity_rows = ops_recent_activity(conn, client_id, limit=80, search=search)
        note_rows = conn.execute(
            '''SELECT jn.*, j.title AS job_title, u.full_name
               FROM job_notes jn
               LEFT JOIN jobs j ON j.id = jn.job_id
               LEFT JOIN users u ON u.id = jn.created_by_user_id
               WHERE jn.client_id=?
               ORDER BY jn.created_at DESC, jn.id DESC
               LIMIT 80''',
            (client_id,),
        ).fetchall()
    return render_template(
        'ops_activity.html',
        client=client,
        client_id=client_id,
        activity_rows=activity_rows,
        note_rows=note_rows,
        search=search,
    )


@app.route('/locations', methods=['GET', 'POST'])
@login_required
def ops_locations():
    user = current_user()
    client_id = selected_client_id(user, 'post' if request.method == 'POST' else 'get')
    selected_location_id = request.values.get('location_id', type=int)
    if request.method == 'POST':
        action = (request.form.get('action') or 'save_location').strip()
        with get_conn() as conn:
            prepare_ops_workspace(conn, client_id)
            if action == 'save_location':
                location_id = request.form.get('location_id', type=int)
                payload = (
                    (request.form.get('location_name', '') or '').strip(),
                    (request.form.get('address_line1', '') or '').strip(),
                    (request.form.get('city', '') or '').strip(),
                    (request.form.get('state', '') or '').strip(),
                    (request.form.get('postal_code', '') or '').strip(),
                    (request.form.get('access_notes', '') or '').strip(),
                    (request.form.get('gate_code', '') or '').strip(),
                    (request.form.get('parking_notes', '') or '').strip(),
                    (request.form.get('location_notes', '') or '').strip(),
                    now_iso(),
                )
                if location_id:
                    conn.execute(
                        '''UPDATE service_locations
                           SET location_name=?, address_line1=?, city=?, state=?, postal_code=?, access_notes=?, gate_code=?, parking_notes=?, location_notes=?, updated_at=?
                           WHERE id=? AND client_id=?''',
                        payload + (location_id, client_id),
                    )
                    selected_location_id = location_id
                else:
                    conn.execute(
                        '''INSERT INTO service_locations (
                               client_id, location_name, address_line1, city, state, postal_code, access_notes, gate_code, parking_notes, location_notes, updated_at
                           ) VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                        (client_id,) + payload,
                    )
                    selected_location_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
                conn.commit()
                flash('Location saved.', 'success')
            elif action == 'delete_location':
                location_id = request.form.get('location_id', type=int)
                linked_job = conn.execute('SELECT 1 FROM jobs WHERE service_location_id=? LIMIT 1', (location_id,)).fetchone()
                if linked_job:
                    flash('Location is linked to jobs and cannot be removed.', 'error')
                else:
                    conn.execute('DELETE FROM service_locations WHERE id=? AND client_id=?', (location_id, client_id))
                    conn.commit()
                    flash('Location removed.', 'success')
        return redirect(url_for('ops_locations', client_id=client_id, location_id=selected_location_id))
    with get_conn() as conn:
        prepare_ops_workspace(conn, client_id)
        client = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
        locations = conn.execute(
            '''SELECT sl.*, COUNT(j.id) AS job_count, MAX(substr(COALESCE(j.scheduled_start, ''), 1, 10)) AS last_job_date
               FROM service_locations sl
               LEFT JOIN jobs j ON j.service_location_id = sl.id
               WHERE sl.client_id=?
               GROUP BY sl.id
               ORDER BY sl.location_name, sl.address_line1''',
            (client_id,),
        ).fetchall()
        selected_location_id = selected_location_id or (locations[0]['id'] if locations else None)
        selected_location = conn.execute('SELECT * FROM service_locations WHERE id=? AND client_id=?', (selected_location_id, client_id)).fetchone() if selected_location_id else None
        location_jobs = conn.execute(
            '''SELECT title, status, scheduled_start
               FROM jobs
               WHERE client_id=? AND service_location_id=?
               ORDER BY COALESCE(scheduled_start, '') DESC, id DESC
               LIMIT 20''',
            (client_id, selected_location_id),
        ).fetchall() if selected_location_id else []
    return render_template(
        'ops_locations.html',
        client=client,
        client_id=client_id,
        locations=locations,
        selected_location=selected_location,
        location_jobs=location_jobs,
    )


@app.route('/templates', methods=['GET', 'POST'])
@login_required
def ops_templates():
    user = current_user()
    client_id = selected_client_id(user, 'post' if request.method == 'POST' else 'get')
    selected_template_id = request.values.get('template_id', type=int)
    if request.method == 'POST':
        action = (request.form.get('action') or 'save_template').strip()
        with get_conn() as conn:
            prepare_ops_workspace(conn, client_id)
            if action == 'save_template':
                template_id = request.form.get('template_id', type=int)
                payload = (
                    ops_int(request.form.get('service_type_id')),
                    (request.form.get('name', '') or '').strip(),
                    (request.form.get('default_title', '') or '').strip(),
                    max(ops_int(request.form.get('default_duration_minutes'), 120) or 120, 0),
                    normalize_ops_priority(request.form.get('default_priority')),
                    max(ops_int(request.form.get('default_crew_size'), 1) or 1, 1),
                    ops_clean_csv(request.form.get('default_tags', '')),
                    (request.form.get('default_notes', '') or '').strip(),
                    (request.form.get('checklist_text', '') or '').strip(),
                    1 if request.form.get('is_active') else 0,
                    now_iso(),
                )
                if not payload[1]:
                    flash('Template name is required.', 'error')
                elif template_id:
                    conn.execute(
                        '''UPDATE job_templates
                           SET service_type_id=?, name=?, default_title=?, default_duration_minutes=?, default_priority=?, default_crew_size=?,
                               default_tags=?, default_notes=?, checklist_text=?, is_active=?, updated_at=?
                           WHERE id=? AND client_id=?''',
                        payload + (template_id, client_id),
                    )
                    selected_template_id = template_id
                    conn.commit()
                    flash('Template updated.', 'success')
                else:
                    conn.execute(
                        '''INSERT INTO job_templates (
                               client_id, service_type_id, name, default_title, default_duration_minutes, default_priority,
                               default_crew_size, default_tags, default_notes, checklist_text, is_active, updated_at
                           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (client_id,) + payload,
                    )
                    selected_template_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
                    conn.commit()
                    flash('Template created.', 'success')
            elif action == 'delete_template':
                template_id = request.form.get('template_id', type=int)
                conn.execute('UPDATE job_templates SET is_active=0, updated_at=? WHERE id=? AND client_id=?', (now_iso(), template_id, client_id))
                conn.commit()
                flash('Template archived.', 'success')
        return redirect(url_for('ops_templates', client_id=client_id, template_id=selected_template_id))
    with get_conn() as conn:
        prepare_ops_workspace(conn, client_id)
        client = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
        service_types = ops_service_types(conn, client_id)
        templates = ops_job_templates(conn, client_id)
        selected_template_id = selected_template_id or (templates[0]['id'] if templates else None)
        selected_template = conn.execute('SELECT * FROM job_templates WHERE id=? AND client_id=?', (selected_template_id, client_id)).fetchone() if selected_template_id else None
    return render_template(
        'ops_templates.html',
        client=client,
        client_id=client_id,
        service_types=service_types,
        templates=templates,
        selected_template=selected_template,
        priority_options=ops_priority_options(),
    )


@app.route('/welcome-center')
@login_required
def welcome_center():
    user = current_user()
    client_id = selected_client_id(user, 'get')
    with get_conn() as conn:
        client = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
        worker_count_row = conn.execute('SELECT COUNT(*) count FROM workers WHERE client_id=?', (client_id,)).fetchone()
    owner_name = (client['contact_name'] or '').strip() if client else ''
    summary = client_summary(client_id) if client else {}
    return render_template(
        'welcome_center.html',
        client=client,
        client_id=client_id,
        needs_onboarding=user_requires_business_onboarding(user),
        user_name=user['full_name'],
        owner_name=owner_name or user['full_name'],
        business_name=(client['business_name'] if client else ''),
        video_topics=welcome_center_video_topics(),
        summary=summary,
        worker_count=int(worker_count_row['count'] or 0) if worker_count_row else 0,
    )


@app.route('/summary')
@login_required
def summary():
    user = current_user()
    client_id = selected_client_id(user, 'get')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    with get_conn() as conn:
        client = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
        workers = conn.execute('SELECT * FROM workers WHERE client_id=? ORDER BY CASE WHEN status="active" THEN 0 ELSE 1 END, name', (client_id,)).fetchall()
        invoices = conn.execute(
            "SELECT * FROM invoices WHERE client_id=? AND COALESCE(record_kind,'income_record')<>'estimate' ORDER BY invoice_date DESC LIMIT 8",
            (client_id,),
        ).fetchall()
        mileage = conn.execute('SELECT * FROM mileage_entries WHERE client_id=? ORDER BY trip_date DESC LIMIT 8', (client_id,)).fetchall()
    return render_template('summary.html', client=client, client_id=client_id, workers=workers, invoices=invoices, mileage_entries=mileage, summary=client_summary(client_id, start_date or None, end_date or None), start_date=start_date, end_date=end_date)


@app.route('/clients-sales', methods=['GET', 'POST'])
@login_required
def customer_sales():
    user = current_user()
    client_id = selected_client_id(user, 'post' if request.method == 'POST' else 'get')
    frequency_values = {value for value, _label in recurring_frequency_options()}
    weekday_values = {value for value, _label in recurring_weekday_options()}
    with get_conn() as conn:
        client = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
        if not client or not allowed_client(user, client_id):
            abort(403)
        if not premium_sales_access_enabled(client):
            return premium_sales_redirect(client_id)
        if request.method == 'POST':
            action = (request.form.get('action', 'add_customer_contact') or '').strip()
            if action == 'add_customer_contact':
                customer_name = request.form.get('customer_name', '').strip()
                customer_email = request.form.get('customer_email', '').strip().lower()
                customer_phone = request.form.get('customer_phone', '').strip()
                customer_address = request.form.get('customer_address', '').strip()
                customer_notes = request.form.get('customer_notes', '').strip()
                recurring_frequency = (request.form.get('recurring_frequency', '') or '').strip().lower()
                recurring_weekday = (request.form.get('recurring_weekday', '') or '').strip()
                recurring_start_date = (request.form.get('recurring_start_date', '') or '').strip()
                recurring_end_date = (request.form.get('recurring_end_date', '') or '').strip()
                recurring_job_name = (request.form.get('recurring_job_name', '') or '').strip()
                recurring_scope = (request.form.get('recurring_scope', '') or '').strip()
                recurring_start_time = (request.form.get('recurring_start_time', '') or '').strip()
                recurring_end_time = (request.form.get('recurring_end_time', '') or '').strip()
                recurring_estimated_duration = (request.form.get('recurring_estimated_duration', '') or '').strip()
                recurring_expected_amount = request.form.get('recurring_expected_amount', type=float)
                if recurring_expected_amount is None:
                    recurring_expected_amount = 0.0
                if not customer_name:
                    flash('Client name is required.', 'error')
                    return redirect(url_for('customer_sales', client_id=client_id))
                if customer_email and '@' not in customer_email:
                    flash('Enter a valid client email or leave it blank.', 'error')
                    return redirect(url_for('customer_sales', client_id=client_id))
                if recurring_frequency not in frequency_values:
                    flash('Choose a valid recurring frequency.', 'error')
                    return redirect(url_for('customer_sales', client_id=client_id))
                if recurring_weekday and recurring_weekday not in weekday_values:
                    flash('Choose a valid service day.', 'error')
                    return redirect(url_for('customer_sales', client_id=client_id))
                if recurring_start_date and not parse_date(recurring_start_date):
                    flash('Service start date is invalid.', 'error')
                    return redirect(url_for('customer_sales', client_id=client_id))
                if recurring_end_date and not parse_date(recurring_end_date):
                    flash('Service end date is invalid.', 'error')
                    return redirect(url_for('customer_sales', client_id=client_id))
                if recurring_end_date and recurring_start_date and parse_date(recurring_end_date) and parse_date(recurring_start_date) and parse_date(recurring_end_date) < parse_date(recurring_start_date):
                    flash('Service end date must be on or after the start date.', 'error')
                    return redirect(url_for('customer_sales', client_id=client_id))
                if recurring_expected_amount < 0:
                    flash('Default visit price cannot be negative.', 'error')
                    return redirect(url_for('customer_sales', client_id=client_id))
                saved_contact_id = upsert_customer_contact(
                    conn,
                    client_id=client_id,
                    customer_name=customer_name,
                    customer_email=customer_email,
                    customer_phone=customer_phone,
                    customer_address=customer_address,
                    customer_notes=customer_notes,
                    created_by_user_id=user['id'],
                )
                if saved_contact_id:
                    conn.execute(
                        '''UPDATE customer_contacts
                           SET recurring_frequency=?,
                               recurring_weekday=?,
                               recurring_start_date=?,
                               recurring_end_date=?,
                               recurring_job_name=?,
                               recurring_scope=?,
                               recurring_start_time=?,
                               recurring_end_time=?,
                               recurring_estimated_duration=?,
                               recurring_expected_amount=?,
                               auto_add_to_calendar=?,
                               updated_at=?,
                               updated_by_user_id=?
                           WHERE id=? AND client_id=?''',
                        (
                            recurring_frequency,
                            recurring_weekday if recurring_frequency else '',
                            recurring_start_date if recurring_frequency else '',
                            recurring_end_date if recurring_frequency else '',
                            recurring_job_name if recurring_frequency else '',
                            recurring_scope if recurring_frequency else '',
                            recurring_start_time if recurring_frequency else '',
                            recurring_end_time if recurring_frequency else '',
                            recurring_estimated_duration if recurring_frequency else '',
                            money(recurring_expected_amount or 0),
                            1 if (recurring_frequency and request.form.get('auto_add_to_calendar')) else 0,
                            now_iso(),
                            user['id'],
                            saved_contact_id,
                            client_id,
                        ),
                    )
                created_schedule_count = ensure_recurring_schedule_entries(conn, client_id=client_id, actor_user_id=user['id'])
                conn.commit()
                if created_schedule_count:
                    flash(f'Client saved. {created_schedule_count} recurring visit(s) were added to the calendar.', 'success')
                else:
                    flash('Client saved.', 'success')
                return redirect(url_for('customer_sales', client_id=client_id))
            if action == 'update_customer_contact':
                contact_id = request.form.get('contact_id', type=int)
                contact = conn.execute(
                    'SELECT * FROM customer_contacts WHERE id=? AND client_id=?',
                    (contact_id, client_id),
                ).fetchone() if contact_id else None
                if not contact:
                    flash('Client record not found.', 'error')
                    return redirect(url_for('customer_sales', client_id=client_id))
                customer_name = request.form.get('customer_name', '').strip()
                customer_email = request.form.get('customer_email', '').strip().lower()
                recurring_frequency = (request.form.get('recurring_frequency', '') or '').strip().lower()
                recurring_weekday = (request.form.get('recurring_weekday', '') or '').strip()
                recurring_start_date = (request.form.get('recurring_start_date', '') or '').strip()
                recurring_end_date = (request.form.get('recurring_end_date', '') or '').strip()
                recurring_job_name = (request.form.get('recurring_job_name', '') or '').strip()
                recurring_scope = (request.form.get('recurring_scope', '') or '').strip()
                recurring_start_time = (request.form.get('recurring_start_time', '') or '').strip()
                recurring_end_time = (request.form.get('recurring_end_time', '') or '').strip()
                recurring_estimated_duration = (request.form.get('recurring_estimated_duration', '') or '').strip()
                recurring_expected_amount = request.form.get('recurring_expected_amount', type=float)
                if recurring_expected_amount is None:
                    recurring_expected_amount = 0.0
                if not customer_name:
                    flash('Client name is required.', 'error')
                    return redirect(url_for('customer_sales', client_id=client_id))
                if customer_email and '@' not in customer_email:
                    flash('Enter a valid client email or leave it blank.', 'error')
                    return redirect(url_for('customer_sales', client_id=client_id))
                if recurring_frequency not in frequency_values:
                    flash('Choose a valid recurring frequency.', 'error')
                    return redirect(url_for('customer_sales', client_id=client_id))
                if recurring_weekday and recurring_weekday not in weekday_values:
                    flash('Choose a valid service day.', 'error')
                    return redirect(url_for('customer_sales', client_id=client_id))
                if recurring_start_date and not parse_date(recurring_start_date):
                    flash('Service start date is invalid.', 'error')
                    return redirect(url_for('customer_sales', client_id=client_id))
                if recurring_end_date and not parse_date(recurring_end_date):
                    flash('Service end date is invalid.', 'error')
                    return redirect(url_for('customer_sales', client_id=client_id))
                if recurring_end_date and recurring_start_date and parse_date(recurring_end_date) and parse_date(recurring_start_date) and parse_date(recurring_end_date) < parse_date(recurring_start_date):
                    flash('Service end date must be on or after the start date.', 'error')
                    return redirect(url_for('customer_sales', client_id=client_id))
                if recurring_expected_amount < 0:
                    flash('Default visit price cannot be negative.', 'error')
                    return redirect(url_for('customer_sales', client_id=client_id))
                conn.execute(
                    '''UPDATE customer_contacts
                       SET customer_name=?,
                           customer_email=?,
                           customer_phone=?,
                           customer_address=?,
                           customer_notes=?,
                           recurring_frequency=?,
                           recurring_weekday=?,
                           recurring_start_date=?,
                           recurring_end_date=?,
                           recurring_job_name=?,
                           recurring_scope=?,
                           recurring_start_time=?,
                           recurring_end_time=?,
                           recurring_estimated_duration=?,
                           recurring_expected_amount=?,
                           auto_add_to_calendar=?,
                           updated_at=?,
                           updated_by_user_id=?
                       WHERE id=? AND client_id=?''',
                    (
                        customer_name,
                        customer_email,
                        request.form.get('customer_phone', '').strip(),
                        request.form.get('customer_address', '').strip(),
                        request.form.get('customer_notes', '').strip(),
                        recurring_frequency,
                        recurring_weekday if recurring_frequency else '',
                        recurring_start_date if recurring_frequency else '',
                        recurring_end_date if recurring_frequency else '',
                        recurring_job_name if recurring_frequency else '',
                        recurring_scope if recurring_frequency else '',
                        recurring_start_time if recurring_frequency else '',
                        recurring_end_time if recurring_frequency else '',
                        recurring_estimated_duration if recurring_frequency else '',
                        money(recurring_expected_amount or 0),
                        1 if (recurring_frequency and request.form.get('auto_add_to_calendar')) else 0,
                        now_iso(),
                        user['id'],
                        contact_id,
                        client_id,
                    ),
                )
                created_schedule_count = ensure_recurring_schedule_entries(conn, client_id=client_id, actor_user_id=user['id'])
                conn.commit()
                if created_schedule_count:
                    flash(f'Client updated. {created_schedule_count} recurring visit(s) were added to the calendar.', 'success')
                else:
                    flash('Client updated.', 'success')
                return redirect(url_for('customer_sales', client_id=client_id))
            if action in {'archive_customer_contact', 'restore_customer_contact'}:
                contact_id = request.form.get('contact_id', type=int)
                next_status = 'archived' if action == 'archive_customer_contact' else 'active'
                updated = conn.execute(
                    '''UPDATE customer_contacts
                       SET status=?,
                           updated_at=?,
                           updated_by_user_id=?
                       WHERE id=? AND client_id=?''',
                    (next_status, now_iso(), user['id'], contact_id, client_id),
                )
                conn.commit()
                if updated.rowcount:
                    flash('Client record updated.', 'success')
                else:
                    flash('Client record not found.', 'error')
                return redirect(url_for('customer_sales', client_id=client_id))
            if action == 'delete_customer_contact':
                contact_id = request.form.get('contact_id', type=int)
                contact = conn.execute(
                    'SELECT * FROM customer_contacts WHERE id=? AND client_id=?',
                    (contact_id, client_id),
                ).fetchone() if contact_id else None
                if not contact:
                    flash('Client record not found.', 'error')
                    return redirect(url_for('customer_sales', client_id=client_id))
                dependency = customer_contact_dependency_summary(conn, client_id, contact_id)
                if (contact['status'] or 'active') == 'active':
                    flash('Archive the client first before permanent deletion.', 'error')
                    return redirect(url_for('customer_sales', client_id=client_id))
                if not dependency['can_delete']:
                    flash('This client has linked invoices, estimates, jobs, or schedule entries and cannot be permanently deleted yet.', 'error')
                    return redirect(url_for('customer_sales', client_id=client_id))
                conn.execute('DELETE FROM customer_contacts WHERE id=? AND client_id=?', (contact_id, client_id))
                conn.commit()
                flash('Client record deleted permanently.', 'success')
                return redirect(url_for('customer_sales', client_id=client_id))
        ensure_recurring_schedule_entries(conn, client_id=client_id, actor_user_id=user['id'])
        conn.commit()
        contact_rows = conn.execute(
            '''SELECT *
               FROM customer_contacts
               WHERE client_id=?
               ORDER BY CASE WHEN COALESCE(status,'active')='active' THEN 0 ELSE 1 END,
                        LOWER(customer_name), id DESC''',
            (client_id,),
        ).fetchall()
        active_contacts = [dict(row) for row in contact_rows if (row['status'] or 'active') == 'active']
        archived_contacts = [dict(row) for row in contact_rows if (row['status'] or 'active') != 'active']
        estimate_source_rows = conn.execute(
            "SELECT * FROM invoices WHERE client_id=? AND COALESCE(record_kind,'')='estimate' ORDER BY invoice_date DESC, id DESC LIMIT 10",
            (client_id,),
        ).fetchall()
        invoice_source_rows = conn.execute(
            "SELECT * FROM invoices WHERE client_id=? AND COALESCE(record_kind,'')='customer_invoice' ORDER BY invoice_date DESC, id DESC LIMIT 10",
            (client_id,),
        ).fetchall()
        estimate_rows = []
        estimate_public_links = {}
        invoice_rows = []
        invoice_public_links = {}
        customer_activity_map: dict[tuple[str, str], dict] = {}
        recurring_schedule_map = {
            row['customer_contact_id']: dict(row) for row in conn.execute(
                '''SELECT customer_contact_id,
                          COUNT(*) upcoming_count,
                          MIN(schedule_date) next_visit,
                          COALESCE(SUM(expected_amount),0) projected_window_amount
                   FROM work_schedule_entries
                   WHERE client_id=?
                     AND COALESCE(auto_generated,0)=1
                     AND schedule_date>=?
                     AND customer_contact_id IS NOT NULL
                   GROUP BY customer_contact_id''',
                (client_id, date.today().isoformat()),
            ).fetchall()
        }
        metrics = {
            'customer_count': 0,
            'open_estimates': 0,
            'approved_estimates': 0,
            'open_invoices': 0,
            'projected_recurring_revenue': 0.0,
            'upcoming_recurring_visits': 0,
        }

        for contact in contact_rows:
            contact_name = (contact['customer_name'] or '').strip() or 'Unnamed client'
            contact_email = (contact['customer_email'] or '').strip().lower()
            customer_activity_map[(contact_name.lower(), contact_email)] = {
                'customer_name': contact_name,
                'customer_email': contact_email,
                'customer_phone': (contact['customer_phone'] or '').strip(),
                'customer_address': (contact['customer_address'] or '').strip(),
                'customer_notes': (contact['customer_notes'] or '').strip(),
                'estimate_count': 0,
                'invoice_count': 0,
                'last_estimate_status': '',
                'last_invoice_status': '',
                'last_activity_at': contact['updated_at'] or contact['created_at'] or '',
                'open_balance': 0.0,
                'source': 'saved_client',
                'status': contact['status'] or 'active',
            }

        for row in estimate_source_rows:
            token = ensure_invoice_public_token(conn, row['id'])
            status = estimate_current_status(row)
            row_dict = dict(row)
            row_dict['invoice_status'] = status
            estimate_rows.append(row_dict)
            estimate_public_links[row['id']] = public_estimate_url(token)
            if status in {'draft', 'sent', 'viewed'}:
                metrics['open_estimates'] += 1
            if status == 'approved':
                metrics['approved_estimates'] += 1
            customer_name = (row['client_name'] or '').strip() or 'Unnamed customer'
            customer_email = (row['recipient_email'] or '').strip().lower()
            key = (customer_name.lower(), customer_email)
            activity = customer_activity_map.setdefault(key, {
                'customer_name': customer_name,
                'customer_email': customer_email,
                'customer_phone': '',
                'customer_address': '',
                'customer_notes': '',
                'estimate_count': 0,
                'invoice_count': 0,
                'last_estimate_status': '',
                'last_invoice_status': '',
                'last_activity_at': '',
                'open_balance': 0.0,
                'source': 'sales_activity',
                'status': 'active',
            })
            activity['estimate_count'] += 1
            activity['last_estimate_status'] = status
            activity['last_activity_at'] = max(activity['last_activity_at'], row['updated_at'] or row['invoice_date'] or '')

        for row in invoice_source_rows:
            token = ensure_invoice_public_token(conn, row['id'])
            status = invoice_payment_progress_status(row)
            balance_due = invoice_balance_due(row)
            row_dict = dict(row)
            row_dict['invoice_status'] = status
            row_dict['balance_due'] = balance_due
            invoice_rows.append(row_dict)
            invoice_public_links[row['id']] = public_invoice_url(token)
            if balance_due > 0:
                metrics['open_invoices'] += 1
            customer_name = (row['client_name'] or '').strip() or 'Unnamed customer'
            customer_email = (row['recipient_email'] or '').strip().lower()
            key = (customer_name.lower(), customer_email)
            activity = customer_activity_map.setdefault(key, {
                'customer_name': customer_name,
                'customer_email': customer_email,
                'customer_phone': '',
                'customer_address': '',
                'customer_notes': '',
                'estimate_count': 0,
                'invoice_count': 0,
                'last_estimate_status': '',
                'last_invoice_status': '',
                'last_activity_at': '',
                'open_balance': 0.0,
                'source': 'sales_activity',
                'status': 'active',
            })
            activity['invoice_count'] += 1
            activity['last_invoice_status'] = status
            activity['open_balance'] += balance_due
            activity['last_activity_at'] = max(activity['last_activity_at'], row['updated_at'] or row['invoice_date'] or '')

    customer_activity = sorted(
        customer_activity_map.values(),
        key=lambda item: (item['last_activity_at'] or '', item['customer_name'].lower()),
        reverse=True,
    )
    recurring_frequency_labels = dict(recurring_frequency_options())
    for contact in active_contacts:
        schedule_rollup = recurring_schedule_map.get(contact['id'])
        contact['projected_monthly'] = projected_recurring_monthly_amount(contact)
        if (contact.get('recurring_frequency') or '').strip():
            next_dates = recurring_occurrence_dates(contact, window_start=date.today(), horizon_days=42, limit=1)
            contact['next_visit'] = (schedule_rollup or {}).get('next_visit') or (next_dates[0].isoformat() if next_dates else '')
        else:
            contact['next_visit'] = ''
        contact['upcoming_recurring_visits'] = int((schedule_rollup or {}).get('upcoming_count') or 0)
        contact['projected_window_amount'] = money((schedule_rollup or {}).get('projected_window_amount') or 0)
        metrics['projected_recurring_revenue'] += float(contact['projected_monthly'] or 0)
        metrics['upcoming_recurring_visits'] += int(contact['upcoming_recurring_visits'] or 0)
    metrics['customer_count'] = len(active_contacts)
    with get_conn() as dependency_conn:
        archived_dependency_map = {
            row['id']: customer_contact_dependency_summary(dependency_conn, client_id, row['id'])
            for row in archived_contacts
        }
    return render_template(
        'customer_sales.html',
        client=client,
        client_id=client_id,
        customer_contacts=active_contacts,
        archived_customer_contacts=archived_contacts,
        customer_activity=customer_activity,
        estimate_rows=estimate_rows,
        estimate_public_links=estimate_public_links,
        estimate_status_labels=estimate_status_label_map(),
        invoice_rows=invoice_rows,
        invoice_public_links=invoice_public_links,
        invoice_status_labels=invoice_status_label_map(),
        metrics=metrics,
        archived_dependency_map=archived_dependency_map,
        recurring_frequency_options=recurring_frequency_options(),
        recurring_frequency_labels=recurring_frequency_labels,
        recurring_weekday_options=recurring_weekday_options(),
    )


@app.route('/benefits-obligations')
@login_required
def benefits_obligations():
    user = current_user()
    client_id = selected_client_id(user, 'get')
    with get_conn() as conn:
        client = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
    return render_template(
        'benefits_obligations.html',
        client=client,
        client_id=client_id,
        opportunity_sections=business_benefits_opportunities(),
        obligation_sections=business_obligation_guides(),
        official_links=benefits_official_resource_links(),
    )


@app.route('/clients', methods=['GET', 'POST'])
@login_required
def clients():
    user = current_user()
    workspace_mode = str(request.values.get('workspace', '') or '').strip().lower() in {'1', 'true', 'yes', 'on'}
    with get_conn() as conn:
        if request.method == 'POST':
            action = request.form.get('action', 'add').strip().lower()
            if user['role'] != 'admin' and action != 'edit':
                abort(403)
            if action == 'send_rejoin_invite':
                client_id = request.form.get('client_id', type=int)
                existing = conn.execute(
                    'SELECT id, business_name, contact_name, email, record_status FROM clients WHERE id=?',
                    (client_id,)
                ).fetchone() if client_id else None
                if not existing:
                    flash('Business not found.', 'error')
                    return redirect(url_for('clients'))
                if (existing['record_status'] or 'active') != 'archived':
                    flash('Only archived businesses can receive a rejoin invite.', 'error')
                    return redirect(url_for('clients'))
                rejoin_email = normalize_email_address(existing['email'] or '')
                rejoin_name = (existing['contact_name'] or '').strip()
                if not rejoin_email:
                    flash('Add a valid business email before sending a rejoin invite.', 'error')
                    return redirect(url_for('clients'))
                token = generate_invite_token()
                expires_at = (datetime.utcnow() + timedelta(days=14)).strftime('%Y-%m-%d %H:%M:%S')
                conn.execute(
                    'INSERT INTO business_invites (client_id, invited_email, invited_name, token, status, created_by_user_id, expires_at, invite_error) VALUES (?,?,?,?,?,?,?,?)',
                    (client_id, rejoin_email, rejoin_name, token, 'pending', user['id'], expires_at, '')
                )
                invite_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
                rejoin_link = build_rejoin_link(token)
                try:
                    email_payload = send_rejoin_email(rejoin_email, rejoin_name, existing['business_name'], rejoin_link)
                    conn.execute('UPDATE business_invites SET status="sent", invite_error="" WHERE id=?', (invite_id,))
                    conn.commit()
                    log_email_delivery(
                        client_id=client_id,
                        email_type=email_payload['email_type'],
                        recipient_email=rejoin_email,
                        recipient_name=rejoin_name,
                        subject=email_payload['subject'],
                        body_text=email_payload['body_text'],
                        body_html=email_payload['body_html'],
                        status='sent',
                        created_by_user_id=user['id'],
                        related_invite_id=invite_id,
                    )
                    flash(f'Rejoin invite sent to {existing["business_name"]}. View it below in Recent Business Emails.', 'success')
                except Exception as e:
                    conn.execute('UPDATE business_invites SET status="failed", invite_error=? WHERE id=?', (str(e)[:500], invite_id))
                    conn.commit()
                    log_email_delivery(
                        client_id=client_id,
                        email_type='business_rejoin',
                        recipient_email=rejoin_email,
                        recipient_name=rejoin_name,
                        subject=f'LedgerFlow - restore access for {existing["business_name"]}',
                        status='failed',
                        error_message=str(e)[:500],
                        created_by_user_id=user['id'],
                        related_invite_id=invite_id,
                    )
                    flash(f'Rejoin invite email failed: {str(e)[:180]}', 'error')
                return redirect(url_for('clients'))
            if action == 'archive':
                client_id = request.form.get('client_id', type=int)
                archive_reason = normalize_business_archive_reason(request.form.get('archive_reason', ''))
                existing = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone() if client_id else None
                if not existing:
                    flash('Business not found.', 'error')
                    return redirect(url_for('clients'))
                archived_at = now_iso()
                conn.execute(
                    'UPDATE clients SET record_status=?, archive_reason=?, archived_at=?, archived_by_user_id=?, reactivated_at=?, updated_at=?, updated_by_user_id=? WHERE id=?',
                    ('archived', archive_reason, archived_at, user['id'], '', archived_at, user['id'], client_id)
                )
                log_client_profile_history(conn, client_id=client_id, action='archived', changed_by_user_id=user['id'], detail=f"Reason: {archive_reason}")
                conn.commit()
                flash(f'{existing["business_name"]} moved to Archived Businesses.', 'success')
                return redirect(url_for('clients'))
            if action == 'reactivate':
                client_id = request.form.get('client_id', type=int)
                existing = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone() if client_id else None
                if not existing:
                    flash('Business not found.', 'error')
                    return redirect(url_for('clients'))
                reactivated_at = now_iso()
                conn.execute(
                    'UPDATE clients SET record_status=?, reactivated_at=?, updated_at=?, updated_by_user_id=? WHERE id=?',
                    ('active', reactivated_at, reactivated_at, user['id'], client_id)
                )
                log_client_profile_history(conn, client_id=client_id, action='reactivated', changed_by_user_id=user['id'])
                conn.commit()
                flash(f'{existing["business_name"]} reactivated.', 'success')
                return redirect(url_for('clients'))
            if action == 'delete_permanently':
                client_id = request.form.get('client_id', type=int)
                existing = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone() if client_id else None
                if not existing:
                    flash('Business not found.', 'error')
                    return redirect(url_for('clients'))
                if (existing['record_status'] or 'active') != 'archived':
                    flash('Archive the business first before deleting permanently.', 'error')
                    return redirect(url_for('clients'))
                blockers = client_delete_blockers(conn, client_id)
                if blockers:
                    blocker_text = ', '.join(f"{table.replace('_', ' ')} ({count})" for table, count in sorted(blockers.items()))
                    flash(f'Cannot permanently delete {existing["business_name"]} because it still has connected records: {blocker_text}. Keep it archived instead.', 'error')
                    return redirect(url_for('clients'))
                log_client_profile_history(conn, client_id=client_id, action='deleted_permanently', changed_by_user_id=user['id'], snapshot=existing)
                conn.execute('DELETE FROM clients WHERE id=?', (client_id,))
                conn.commit()
                flash(f'{existing["business_name"]} deleted permanently.', 'success')
                return redirect(url_for('clients'))
            service_level = normalize_service_level(request.form.get('service_level', default_service_level()))
            access_service_level = normalize_access_service_level(request.form.get('access_service_level', '')) if user['role'] == 'admin' else ''
            access_override_note = request.form.get('access_override_note', '').strip()[:300] if user['role'] == 'admin' else ''
            if access_service_level == service_level:
                access_service_level = ''
                access_override_note = ''
            business_name = request.form.get('business_name', '').strip()
            business_structure = request.form.get('business_type', '').strip()
            business_category = normalize_business_category(request.form.get('business_category', ''))
            business_specialty = request.form.get('business_specialty', '').strip()[:120]
            owner_contacts = request.form.get('owner_contacts', '').strip()[:1200]
            job_scope_summary = request.form.get('job_scope_summary', '').strip()[:2000]
            values = (
                business_name,
                business_structure,
                business_category,
                business_specialty,
                normalize_language(request.form.get('preferred_language') or 'en'),
                service_level,
                access_service_level,
                access_override_note,
                request.form.get('subscription_plan_code', '').strip(),
                normalize_subscription_status(request.form.get('subscription_status', default_subscription_status())),
                float(normalize_money_amount(request.form.get('subscription_amount', '')) or Decimal('0.00')),
                'monthly',
                1 if request.form.get('subscription_autopay_enabled') in {'1', 'on', 'true', 'yes'} else 0,
                (parse_date(request.form.get('subscription_next_billing_date', '').strip()).isoformat() if parse_date(request.form.get('subscription_next_billing_date', '').strip()) else ''),
                request.form.get('subscription_started_at', '').strip(),
                request.form.get('subscription_canceled_at', '').strip(),
                request.form.get('subscription_paused_at', '').strip(),
                request.form.get('default_payment_method_label', '').strip(),
                normalize_payment_method_status(request.form.get('default_payment_method_status', 'missing')),
                request.form.get('backup_payment_method_label', '').strip(),
                request.form.get('billing_notes', '').strip(),
                request.form.get('contact_name', '').strip(),
                request.form.get('phone', '').strip(),
                request.form.get('email', '').strip().lower(),
                request.form.get('address', '').strip(),
                request.form.get('ein', '').strip(),
                request.form.get('eftps_status', 'Not Enrolled').strip(),
                request.form.get('eftps_login_reference', '').strip(),
                request.form.get('filing_type', 'Both').strip(),
                request.form.get('bank_name', '').strip(),
                request.form.get('bank_account_nickname', '').strip(),
                clean_last4(request.form.get('bank_account_last4', '').strip() or request.form.get('bank_account_number', '').strip()),
                request.form.get('bank_account_holder_name', '').strip(),
                clean_digits(request.form.get('bank_account_number', '').strip()),
                clean_digits(request.form.get('bank_routing_number', '').strip()),
                request.form.get('credit_card_nickname', '').strip(),
                clean_last4(request.form.get('credit_card_last4', '').strip() or request.form.get('credit_card_number', '').strip()),
                request.form.get('credit_card_holder_name', '').strip(),
                clean_digits(request.form.get('credit_card_number', '').strip()),
                request.form.get('payroll_contact_name', '').strip(),
                request.form.get('payroll_contact_phone', '').strip(),
                request.form.get('payroll_contact_email', '').strip().lower(),
                request.form.get('state_tax_id', '').strip(),
                'active',
                '',
                '',
                None,
                '',
            )
            now_value = now_iso()
            if action == 'edit':
                client_id = request.form.get('client_id', type=int)
                existing = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone() if client_id else None
                if user['role'] != 'admin' and int(client_id or 0) != int(user['client_id'] or 0):
                    abort(403)
                if not existing:
                    flash('Business not found.', 'error')
                    return redirect(url_for('clients'))
                if user['role'] != 'admin':
                    values = (
                        business_name,
                        business_structure,
                        business_category,
                        business_specialty,
                        normalize_language(request.form.get('preferred_language') or existing['preferred_language'] or 'en'),
                        service_level,
                        normalize_access_service_level(existing['access_service_level'] or ''),
                        (existing['access_override_note'] or '').strip()[:300],
                        request.form.get('subscription_plan_code', '').strip(),
                        normalize_subscription_status(request.form.get('subscription_status', default_subscription_status())),
                        float(normalize_money_amount(request.form.get('subscription_amount', '')) or Decimal('0.00')),
                        'monthly',
                        1 if request.form.get('subscription_autopay_enabled') in {'1', 'on', 'true', 'yes'} else 0,
                        (parse_date(request.form.get('subscription_next_billing_date', '').strip()).isoformat() if parse_date(request.form.get('subscription_next_billing_date', '').strip()) else ''),
                        request.form.get('subscription_started_at', '').strip(),
                        request.form.get('subscription_canceled_at', '').strip(),
                        request.form.get('subscription_paused_at', '').strip(),
                        request.form.get('default_payment_method_label', '').strip(),
                        normalize_payment_method_status(request.form.get('default_payment_method_status', 'missing')),
                        request.form.get('backup_payment_method_label', '').strip(),
                        request.form.get('billing_notes', '').strip(),
                        request.form.get('contact_name', '').strip(),
                        request.form.get('phone', '').strip(),
                        request.form.get('email', '').strip().lower(),
                        request.form.get('address', '').strip(),
                        request.form.get('ein', '').strip(),
                        request.form.get('eftps_status', 'Not Enrolled').strip(),
                        request.form.get('eftps_login_reference', '').strip(),
                        request.form.get('filing_type', 'Both').strip(),
                        request.form.get('bank_name', '').strip(),
                        request.form.get('bank_account_nickname', '').strip(),
                        clean_last4(request.form.get('bank_account_last4', '').strip() or request.form.get('bank_account_number', '').strip()),
                        request.form.get('bank_account_holder_name', '').strip(),
                        clean_digits(request.form.get('bank_account_number', '').strip()),
                        clean_digits(request.form.get('bank_routing_number', '').strip()),
                        request.form.get('credit_card_nickname', '').strip(),
                        clean_last4(request.form.get('credit_card_last4', '').strip() or request.form.get('credit_card_number', '').strip()),
                        request.form.get('credit_card_holder_name', '').strip(),
                        clean_digits(request.form.get('credit_card_number', '').strip()),
                        request.form.get('payroll_contact_name', '').strip(),
                        request.form.get('payroll_contact_phone', '').strip(),
                        request.form.get('payroll_contact_email', '').strip().lower(),
                        request.form.get('state_tax_id', '').strip(),
                        'active',
                        '',
                        '',
                        None,
                        '',
                    )
                conn.execute(
                    'UPDATE clients SET business_name=?, business_type=?, business_category=?, business_specialty=?, preferred_language=?, service_level=?, access_service_level=?, access_override_note=?, subscription_plan_code=?, subscription_status=?, subscription_amount=?, subscription_interval=?, subscription_autopay_enabled=?, subscription_next_billing_date=?, subscription_started_at=?, subscription_canceled_at=?, subscription_paused_at=?, default_payment_method_label=?, default_payment_method_status=?, backup_payment_method_label=?, billing_notes=?, contact_name=?, phone=?, email=?, address=?, ein=?, eftps_status=?, eftps_login_reference=?, filing_type=?, bank_name=?, bank_account_nickname=?, bank_account_last4=?, bank_account_holder_name=?, bank_account_number=?, bank_routing_number=?, credit_card_nickname=?, credit_card_last4=?, credit_card_holder_name=?, credit_card_number=?, payroll_contact_name=?, payroll_contact_phone=?, payroll_contact_email=?, state_tax_id=?, record_status=?, archive_reason=?, archived_at=?, archived_by_user_id=?, reactivated_at=?, updated_at=?, updated_by_user_id=? WHERE id=?',
                    values + (now_value, user['id'], client_id)
                )
                conn.execute('UPDATE clients SET owner_contacts=?, job_scope_summary=? WHERE id=?', (owner_contacts, job_scope_summary, client_id))
                if user['role'] != 'admin':
                    selected_language = normalize_language(request.form.get('preferred_language') or existing['preferred_language'] or 'en')
                    conn.execute('UPDATE users SET preferred_language=? WHERE id=?', (selected_language, user['id']))
                    session['preferred_language'] = selected_language
                log_client_profile_history(conn, client_id=client_id, action='updated', changed_by_user_id=user['id'])
                conn.commit()
                flash('Business profile updated.', 'success')
                if workspace_mode and user['role'] == 'admin':
                    return redirect(url_for('clients', client_id=client_id, workspace=1))
                return redirect(url_for('clients'))
            conn.execute(
                f'INSERT INTO clients (business_name, business_type, business_category, business_specialty, preferred_language, service_level, access_service_level, access_override_note, subscription_plan_code, subscription_status, subscription_amount, subscription_interval, subscription_autopay_enabled, subscription_next_billing_date, subscription_started_at, subscription_canceled_at, subscription_paused_at, default_payment_method_label, default_payment_method_status, backup_payment_method_label, billing_notes, contact_name, phone, email, address, ein, eftps_status, eftps_login_reference, filing_type, bank_name, bank_account_nickname, bank_account_last4, bank_account_holder_name, bank_account_number, bank_routing_number, credit_card_nickname, credit_card_last4, credit_card_holder_name, credit_card_number, payroll_contact_name, payroll_contact_phone, payroll_contact_email, state_tax_id, record_status, archive_reason, archived_at, archived_by_user_id, reactivated_at, created_by_user_id, updated_at, updated_by_user_id) VALUES ({",".join(["?"] * 51)})',
                values + (user['id'], now_value, user['id'])
            )
            client_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            conn.execute('UPDATE clients SET owner_contacts=?, job_scope_summary=? WHERE id=?', (owner_contacts, job_scope_summary, client_id))
            log_client_profile_history(conn, client_id=client_id, action='created', changed_by_user_id=user['id'])
            conn.commit()
            flash('Business profile created.', 'success')
            return redirect(url_for('clients'))
        if user['role'] == 'admin' and not workspace_mode:
            rows = conn.execute(
                """SELECT c.*, creator.full_name created_by_name, updater.full_name updated_by_name
                   FROM clients c
                   LEFT JOIN users creator ON creator.id = c.created_by_user_id
                   LEFT JOIN users updater ON updater.id = c.updated_by_user_id
                   WHERE COALESCE(c.record_status,'active')='active'
                   ORDER BY c.business_name"""
            ).fetchall()
            prospect_rows = conn.execute("SELECT * FROM clients WHERE COALESCE(record_status,'active')='prospect' ORDER BY business_name").fetchall()
            archived_rows = conn.execute(
                """SELECT
                       c.*,
                       creator.full_name created_by_name,
                       updater.full_name updated_by_name,
                       (
                           SELECT edl.id
                           FROM email_delivery_log edl
                           WHERE edl.client_id = c.id
                             AND edl.email_type = 'business_rejoin'
                           ORDER BY edl.created_at DESC, edl.id DESC
                           LIMIT 1
                       ) AS last_rejoin_email_id,
                       (
                           SELECT edl.status
                           FROM email_delivery_log edl
                           WHERE edl.client_id = c.id
                             AND edl.email_type = 'business_rejoin'
                           ORDER BY edl.created_at DESC, edl.id DESC
                           LIMIT 1
                       ) AS last_rejoin_status,
                       (
                           SELECT edl.created_at
                           FROM email_delivery_log edl
                           WHERE edl.client_id = c.id
                             AND edl.email_type = 'business_rejoin'
                           ORDER BY edl.created_at DESC, edl.id DESC
                           LIMIT 1
                       ) AS last_rejoin_sent_at
                   FROM clients c
                   LEFT JOIN users creator ON creator.id = c.created_by_user_id
                   LEFT JOIN users updater ON updater.id = c.updated_by_user_id
                   WHERE COALESCE(c.record_status,'active')='archived'
                   ORDER BY c.business_name"""
            ).fetchall()
            archived_delete_blockers = {row['id']: client_delete_blockers(conn, row['id']) for row in archived_rows}
        else:
            target_client_id = selected_client_id(user, 'get') if user['role'] == 'admin' else user['client_id']
            row = conn.execute(
                """SELECT c.*, creator.full_name created_by_name, updater.full_name updated_by_name
                   FROM clients c
                   LEFT JOIN users creator ON creator.id = c.created_by_user_id
                   LEFT JOIN users updater ON updater.id = c.updated_by_user_id
                   WHERE c.id=?""",
                (target_client_id,)
            ).fetchone()
            rows = [row] if row else []
            prospect_rows = []
            archived_rows = []
            archived_delete_blockers = {}
    return render_template(
        'clients.html',
        clients=rows,
        prospect_clients=prospect_rows,
        archived_clients=archived_rows,
        archived_delete_blockers=archived_delete_blockers,
        business_structures=business_structures(),
        business_categories=business_categories(),
        service_level_options=service_level_options(),
        service_level_labels=service_level_label_map(),
        subscription_status_options=subscription_status_options(),
        subscription_status_labels=subscription_status_label_map(),
        archive_reason_options=business_archive_reason_options(),
        archive_reason_labels=business_archive_reason_label_map(),
        filing_types=filing_types(),
        eftps_statuses=eftps_statuses(),
        is_admin=(user['role']=='admin' and not workspace_mode),
        mask_account_number=mask_account_number,
        mask_card_number=mask_card_number,
    )


@app.route('/client-logins', methods=['GET', 'POST'])
@admin_required
def client_users():
    user = current_user()
    with get_conn() as conn:
        if request.method == 'POST':
            action = request.form.get('action', 'create_login').strip().lower()
            if action == 'create_login':
                email = request.form.get('email', '').strip().lower()
                password = request.form.get('password', '').strip()
                full_name = request.form.get('full_name', '').strip()
                client_id = request.form.get('client_id', type=int)
                if not email or not password or not full_name or not client_id:
                    flash('Enter full name, email, password, and business before saving.', 'error')
                    return redirect(url_for('client_users'))
                try:
                    business = conn.execute('SELECT business_name, preferred_language FROM clients WHERE id=?', (client_id,)).fetchone()
                    conn.execute(
                        'INSERT INTO users (email, password_hash, full_name, role, client_id, preferred_language) VALUES (?,?,?,?,?,?)',
                        (
                            email,
                            generate_password_hash(password),
                            full_name,
                            'client',
                            client_id,
                            normalize_language((business['preferred_language'] if business else '') or 'en'),
                        )
                    )
                    log_account_activity(conn, client_id=client_id, account_type='business_login', account_email=email, account_name=full_name, created_by_user_id=user['id'], status='auto_approved', detail='Business login created and activated.')
                    conn.commit()
                    welcome_sent = False
                    welcome_error = ''
                    welcome_payload = None
                    if smtp_email_ready():
                        try:
                            welcome_payload = send_welcome_email(
                                email,
                                full_name,
                                'business',
                                login_path='/main-portal',
                                business_name=(business['business_name'] if business else '')
                            )
                            welcome_sent = True
                        except Exception as e:
                            welcome_error = str(e)[:200]
                    if welcome_sent and welcome_payload:
                        log_email_delivery(
                            client_id=client_id,
                            email_type=welcome_payload['email_type'],
                            recipient_email=email,
                            recipient_name=full_name,
                            subject=welcome_payload['subject'],
                            body_text=welcome_payload['body_text'],
                            body_html=welcome_payload['body_html'],
                            status='sent',
                            created_by_user_id=user['id'],
                            related_user_id=conn.execute('SELECT id FROM users WHERE lower(email)=?', (email,)).fetchone()['id'],
                        )
                    elif welcome_error:
                        log_email_delivery(
                            client_id=client_id,
                            email_type='business_welcome',
                            recipient_email=email,
                            recipient_name=full_name,
                            subject=f'Welcome to LedgerFlow - Business Login',
                            status='failed',
                            error_message=welcome_error,
                            created_by_user_id=user['id'],
                            related_user_id=conn.execute('SELECT id FROM users WHERE lower(email)=?', (email,)).fetchone()['id'],
                        )
                    if welcome_sent:
                        flash('Business login created. Welcome email sent. View it below in Recent Business Emails.', 'success')
                    elif smtp_email_ready():
                        flash(f'Business login created, but welcome email failed: {welcome_error}', 'error')
                    else:
                        flash('Business login created.', 'success')
                except sqlite3.IntegrityError:
                    conn.rollback()
                    flash('That email is already in use. Use a different email for this login.', 'error')
                return redirect(url_for('client_users'))
            if action == 'send_prospect_invite':
                business_name = request.form.get('business_name', '').strip()
                invite_name = request.form.get('full_name', '').strip()
                invite_email_raw = request.form.get('email', '').strip()
                invite_email = normalize_email_address(invite_email_raw)
                if not business_name or not invite_name or not invite_email_raw:
                    flash('Enter new customer name, contact name, and email before sending the invite.', 'error')
                    return redirect(url_for('client_users'))
                if not invite_email:
                    flash('Enter a valid customer email before sending the invite.', 'error')
                    return redirect(url_for('client_users'))
                existing_user = conn.execute('SELECT id FROM users WHERE lower(email)=?', (invite_email,)).fetchone()
                if existing_user:
                    flash('That email already has an account. Use a different email for this invite.', 'error')
                    return redirect(url_for('client_users'))
                existing_prospect = conn.execute(
                    "SELECT id FROM clients WHERE lower(email)=? AND COALESCE(record_status,'active')='prospect' ORDER BY id DESC LIMIT 1",
                    (invite_email,)
                ).fetchone()
                if existing_prospect:
                    flash('A prospect invite for this email already exists. Open Prospect Invite Pipeline to resend it.', 'error')
                    return redirect(url_for('client_users'))
                token = generate_invite_token()
                expires_at = (datetime.utcnow() + timedelta(days=14)).strftime('%Y-%m-%d %H:%M:%S')
                now_value = datetime.now().isoformat(timespec='seconds')
                conn.execute(
                    '''INSERT INTO clients (
                           business_name, business_type, service_level, subscription_plan_code, subscription_status,
                           subscription_amount, subscription_interval, subscription_autopay_enabled, subscription_next_billing_date,
                           subscription_started_at, subscription_canceled_at, subscription_paused_at, onboarding_status,
                           onboarding_started_at, onboarding_completed_at, onboarding_completed_by_user_id, record_status,
                           archive_reason, archived_at, archived_by_user_id, reactivated_at, contact_name, email, billing_notes
                       ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (
                        business_name,
                        'Prospect',
                        default_service_level(),
                        '',
                        default_subscription_status(),
                        0.0,
                        'monthly',
                        0,
                        '',
                        '',
                        '',
                        '',
                        'invited',
                        now_value,
                        '',
                        None,
                        'prospect',
                        '',
                        '',
                        None,
                        '',
                        invite_name,
                        invite_email,
                        'Prospect invite created before full business setup.',
                    )
                )
                client_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
                conn.execute(
                    'INSERT INTO business_invites (client_id, invited_email, invited_name, token, status, created_by_user_id, expires_at, invite_error) VALUES (?,?,?,?,?,?,?,?)',
                    (client_id, invite_email, invite_name, token, 'pending', user['id'], expires_at, '')
                )
                invite_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
                invite_link = build_invite_link(token)
                try:
                    invite_payload = send_invite_email(invite_email, invite_name, business_name, invite_link)
                    conn.execute('UPDATE business_invites SET status="sent", invite_error="" WHERE id=?', (invite_id,))
                    conn.commit()
                    log_email_delivery(
                        client_id=client_id,
                        email_type=invite_payload['email_type'],
                        recipient_email=invite_email,
                        recipient_name=invite_name,
                        subject=invite_payload['subject'],
                        body_text=invite_payload['body_text'],
                        body_html=invite_payload['body_html'],
                        status='sent',
                        created_by_user_id=user['id'],
                        related_invite_id=invite_id,
                    )
                    flash('New customer invite sent. The prospect is now tracked until onboarding is completed.', 'success')
                except Exception as e:
                    conn.execute('UPDATE business_invites SET status="failed", invite_error=? WHERE id=?', (str(e)[:500], invite_id))
                    conn.commit()
                    log_email_delivery(
                        client_id=client_id,
                        email_type='business_invite',
                        recipient_email=invite_email,
                        recipient_name=invite_name,
                        subject=f"Welcome to LedgerFlow - set up your business access for {business_name}",
                        status='failed',
                        error_message=str(e)[:500],
                        created_by_user_id=user['id'],
                        related_invite_id=invite_id,
                    )
                    flash(f'New customer invite email failed: {str(e)[:180]}', 'error')
                return redirect(url_for('client_users'))
            if action == 'send_trial_invite':
                business_name = request.form.get('business_name', '').strip()
                invite_name = request.form.get('full_name', '').strip()
                invite_email_raw = request.form.get('email', '').strip()
                invite_email = normalize_email_address(invite_email_raw)
                business_category = normalize_business_category(request.form.get('business_category', ''))
                trial_days = default_trial_offer_days()
                if not business_name or not invite_name or not invite_email_raw:
                    flash('Enter business name, contact name, and email before sending the trial invite.', 'error')
                    return redirect(url_for('client_users'))
                if not invite_email:
                    flash('Enter a valid business email before sending the trial invite.', 'error')
                    return redirect(url_for('client_users'))
                existing_user = conn.execute('SELECT id FROM users WHERE lower(email)=?', (invite_email,)).fetchone()
                if existing_user:
                    flash('That email already has an account. Use a different email for this trial invite.', 'error')
                    return redirect(url_for('client_users'))
                existing_prospect = conn.execute(
                    "SELECT id FROM clients WHERE lower(email)=? AND COALESCE(record_status,'active')='prospect' ORDER BY id DESC LIMIT 1",
                    (invite_email,)
                ).fetchone()
                if existing_prospect:
                    flash('A prospect invite for this email already exists. Open Prospect Invite Pipeline to resend it.', 'error')
                    return redirect(url_for('client_users'))
                token = generate_invite_token()
                expires_at = (datetime.utcnow() + timedelta(days=14)).strftime('%Y-%m-%d %H:%M:%S')
                now_value = datetime.now().isoformat(timespec='seconds')
                conn.execute(
                    '''INSERT INTO clients (
                           business_name, business_type, service_level, subscription_plan_code, subscription_status,
                           subscription_amount, subscription_interval, subscription_autopay_enabled, subscription_next_billing_date,
                           subscription_started_at, subscription_canceled_at, subscription_paused_at, onboarding_status,
                           onboarding_started_at, onboarding_completed_at, onboarding_completed_by_user_id, record_status,
                           archive_reason, archived_at, archived_by_user_id, reactivated_at, contact_name, email, billing_notes,
                           trial_offer_days, trial_started_at, trial_ends_at, business_category
                       ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (
                        business_name,
                        'Prospect',
                        default_service_level(),
                        service_level_plan_code(default_service_level()),
                        default_subscription_status(),
                        0.0,
                        'monthly',
                        0,
                        '',
                        '',
                        '',
                        '',
                        'invited',
                        now_value,
                        '',
                        None,
                        'prospect',
                        '',
                        '',
                        None,
                        '',
                        invite_name,
                        invite_email,
                        f'{trial_days}-day complimentary trial invite created before full business setup.',
                        trial_days,
                        '',
                        '',
                        business_category,
                    )
                )
                client_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
                conn.execute(
                    '''INSERT INTO business_invites (
                           client_id, invited_email, invited_name, token, status, created_by_user_id, expires_at, invite_error, invite_kind, trial_days
                       ) VALUES (?,?,?,?,?,?,?,?,?,?)''',
                    (client_id, invite_email, invite_name, token, 'pending', user['id'], expires_at, '', 'prospect_trial', trial_days)
                )
                invite_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
                invite_link = build_invite_link(token)
                tracking_token = generate_email_tracking_token()
                try:
                    invite_payload = send_trial_invite_email(
                        invite_email,
                        invite_name,
                        business_name,
                        invite_link,
                        trial_days=trial_days,
                        business_category=business_category,
                        tracking_token=tracking_token,
                    )
                    conn.execute('UPDATE business_invites SET status="sent", invite_error="" WHERE id=?', (invite_id,))
                    conn.commit()
                    log_email_delivery(
                        client_id=client_id,
                        email_type=invite_payload['email_type'],
                        recipient_email=invite_email,
                        recipient_name=invite_name,
                        subject=invite_payload['subject'],
                        body_text=invite_payload['body_text'],
                        body_html=invite_payload['body_html'],
                        status='sent',
                        created_by_user_id=user['id'],
                        related_invite_id=invite_id,
                        tracking_token=tracking_token,
                    )
                    flash('7-day trial invite sent. The prospect is now tracked in the pipeline until setup is completed.', 'success')
                except Exception as e:
                    conn.execute('UPDATE business_invites SET status="failed", invite_error=? WHERE id=?', (str(e)[:500], invite_id))
                    conn.commit()
                    log_email_delivery(
                        client_id=client_id,
                        email_type='prospect_trial_invite',
                        recipient_email=invite_email,
                        recipient_name=invite_name,
                        subject=f"Start your {trial_days}-day LedgerFlow trial for {business_name}",
                        status='failed',
                        error_message=str(e)[:500],
                        created_by_user_id=user['id'],
                        related_invite_id=invite_id,
                        tracking_token=tracking_token,
                    )
                    flash(f'Trial invite email failed: {str(e)[:180]}', 'error')
                return redirect(url_for('client_users'))
            if action == 'send_invite':
                client_id = request.form.get('client_id', type=int)
                invite_name = request.form.get('full_name', '').strip()
                invite_email_raw = request.form.get('email', '').strip()
                invite_email = normalize_email_address(invite_email_raw)
                business = conn.execute('SELECT business_name FROM clients WHERE id=?', (client_id,)).fetchone() if client_id else None
                if not business:
                    flash('Choose a valid business before sending the invite.', 'error')
                    return redirect(url_for('client_users'))
                if not invite_name or not invite_email_raw:
                    flash('Enter the invitee name and email before sending the invite.', 'error')
                    return redirect(url_for('client_users'))
                if not invite_email:
                    flash('Enter a valid invitee email before sending the invite.', 'error')
                    return redirect(url_for('client_users'))
                token = generate_invite_token()
                expires_at = (datetime.utcnow() + timedelta(days=14)).strftime('%Y-%m-%d %H:%M:%S')
                conn.execute(
                    'INSERT INTO business_invites (client_id, invited_email, invited_name, token, status, created_by_user_id, expires_at, invite_error, invite_kind, trial_days) VALUES (?,?,?,?,?,?,?,?,?,?)',
                    (client_id, invite_email, invite_name, token, 'pending', user['id'], expires_at, '', 'business_access', 0)
                )
                invite_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
                invite_link = build_invite_link(token)
                try:
                    invite_payload = send_invite_email(invite_email, invite_name, business['business_name'], invite_link)
                    conn.execute('UPDATE business_invites SET status="sent", invite_error="" WHERE id=?', (invite_id,))
                    conn.commit()
                    log_email_delivery(
                        client_id=client_id,
                        email_type=invite_payload['email_type'],
                        recipient_email=invite_email,
                        recipient_name=invite_name,
                        subject=invite_payload['subject'],
                        body_text=invite_payload['body_text'],
                        body_html=invite_payload['body_html'],
                        status='sent',
                        created_by_user_id=user['id'],
                        related_invite_id=invite_id,
                    )
                    flash('Invite sent. View it below in Recent Business Emails.', 'success')
                except Exception as e:
                    conn.execute('UPDATE business_invites SET status="failed", invite_error=? WHERE id=?', (str(e)[:500], invite_id))
                    conn.commit()
                    log_email_delivery(
                        client_id=client_id,
                        email_type='business_invite',
                        recipient_email=invite_email,
                        recipient_name=invite_name,
                        subject=f"Welcome to LedgerFlow - set up your business access for {business['business_name']}",
                        status='failed',
                        error_message=str(e)[:500],
                        created_by_user_id=user['id'],
                        related_invite_id=invite_id,
                    )
                    flash(f'Invite email failed: {str(e)[:180]}', 'error')
                return redirect(url_for('client_users'))
            if action == 'resend_invite':
                invite_id = request.form.get('invite_id', type=int)
                inv = conn.execute(
                    '''SELECT
                           bi.*,
                           c.business_name,
                           c.business_category,
                           c.email AS client_email,
                           COALESCE(c.record_status, 'active') AS business_record_status
                       FROM business_invites bi
                       JOIN clients c ON c.id=bi.client_id
                       WHERE bi.id=?''',
                    (invite_id,)
                ).fetchone()
                if not inv:
                    flash('Invite not found.', 'error')
                    return redirect(url_for('client_users'))
                invite_link = build_invite_link(inv['token'])
                renewed_expires_at = (datetime.utcnow() + timedelta(days=14)).strftime('%Y-%m-%d %H:%M:%S')
                tracking_token = generate_email_tracking_token()
                recipient_email, recipient_note = resolve_invite_recipient_email(inv['invited_email'], inv['client_email'] or '')
                if not recipient_email:
                    conn.execute('UPDATE business_invites SET status="failed", invite_error=? WHERE id=?', (recipient_note, invite_id))
                    conn.commit()
                    flash(recipient_note, 'error')
                    return redirect(url_for('client_users'))
                if recipient_email != normalize_email_address(inv['invited_email'] or ''):
                    conn.execute('UPDATE business_invites SET invited_email=?, invite_error=? WHERE id=?', (recipient_email, recipient_note, invite_id))
                    inv = dict(inv)
                    inv['invited_email'] = recipient_email
                try:
                    if normalize_invite_kind(inv['invite_kind']) == 'prospect_trial':
                        invite_payload = send_trial_invite_email(
                            recipient_email,
                            inv['invited_name'],
                            inv['business_name'],
                            invite_link,
                            trial_days=int(inv['trial_days'] or 0),
                            business_category=inv['business_category'] or '',
                            tracking_token=tracking_token,
                        )
                    else:
                        invite_payload = send_invite_email(recipient_email, inv['invited_name'], inv['business_name'], invite_link)
                    if normalize_invite_kind(inv['invite_kind']) == 'prospect_trial':
                        conn.execute(
                            'UPDATE business_invites SET status="sent", invite_error="", created_at=CURRENT_TIMESTAMP, expires_at=?, followup_sent_at="", followup_status="pending", followup_error="" WHERE id=?',
                            (renewed_expires_at, invite_id),
                        )
                    else:
                        conn.execute('UPDATE business_invites SET status="sent", invite_error="" WHERE id=?', (invite_id,))
                    conn.commit()
                    log_email_delivery(
                        client_id=inv['client_id'],
                        email_type=invite_payload['email_type'],
                        recipient_email=recipient_email,
                        recipient_name=inv['invited_name'],
                        subject=invite_payload['subject'],
                        body_text=invite_payload['body_text'],
                        body_html=invite_payload['body_html'],
                        status='sent',
                        created_by_user_id=user['id'],
                        related_invite_id=invite_id,
                        tracking_token=tracking_token if normalize_invite_kind(inv['invite_kind']) == 'prospect_trial' else '',
                    )
                    if recipient_note:
                        flash(f'Invite re-sent. {recipient_note}', 'success')
                    else:
                        flash('Invite re-sent. View it below in Recent Business Emails.', 'success')
                except Exception as e:
                    conn.execute('UPDATE business_invites SET status="failed", invite_error=? WHERE id=?', (str(e)[:500], invite_id))
                    conn.commit()
                    log_email_delivery(
                        client_id=inv['client_id'],
                        email_type='prospect_trial_invite' if normalize_invite_kind(inv['invite_kind']) == 'prospect_trial' else 'business_invite',
                        recipient_email=recipient_email,
                        recipient_name=inv['invited_name'],
                        subject=(
                            f"Start your {int(inv['trial_days'] or default_trial_offer_days())}-day LedgerFlow trial for {inv['business_name']}"
                            if normalize_invite_kind(inv['invite_kind']) == 'prospect_trial' else
                            f"Welcome to LedgerFlow - set up your business access for {inv['business_name']}"
                        ),
                        status='failed',
                        error_message=str(e)[:500],
                        created_by_user_id=user['id'],
                        related_invite_id=invite_id,
                        tracking_token=tracking_token if normalize_invite_kind(inv['invite_kind']) == 'prospect_trial' else '',
                    )
                    flash(f'Invite email failed: {str(e)[:180]}', 'error')
                return redirect(url_for('client_users'))
        active_clients = conn.execute("SELECT * FROM clients WHERE COALESCE(record_status,'active')='active' ORDER BY business_name").fetchall()
        users = conn.execute('SELECT u.*, c.business_name FROM users u LEFT JOIN clients c ON c.id=u.client_id WHERE u.role="client" ORDER BY c.business_name, u.full_name').fetchall()
        invites = conn.execute(
            """SELECT
                   bi.*,
                   c.business_name,
                   COALESCE(c.record_status,'active') AS business_record_status,
                   c.onboarding_status,
                   c.onboarding_completed_at,
                   c.subscription_status,
                   c.service_level,
                   creator.full_name created_by_name,
                   accepted.full_name accepted_user_name,
                   accepted.email accepted_user_email,
                   completed.full_name onboarding_completed_by_name
               FROM business_invites bi
               JOIN clients c ON c.id=bi.client_id
               LEFT JOIN users creator ON creator.id=bi.created_by_user_id
               LEFT JOIN users accepted ON accepted.id=bi.accepted_user_id
               LEFT JOIN users completed ON completed.id=c.onboarding_completed_by_user_id
               WHERE COALESCE(c.record_status,'active')<>'archived'
               ORDER BY bi.created_at DESC, bi.id DESC"""
        ).fetchall()
        prospect_clients = conn.execute(
            """SELECT
                   c.*,
                   bi.id invite_id,
                   bi.invited_email invite_email,
                   bi.invited_name invite_name,
                   bi.token invite_token,
                   bi.status invite_status,
                   bi.accepted_user_id invite_accepted_user_id,
                   bi.invite_error,
                   bi.invite_kind,
                   bi.trial_days,
                   bi.created_at invite_created_at,
                   bi.expires_at invite_expires_at,
                   bi.used_at invite_used_at,
                   creator.full_name invite_created_by_name,
                   accepted.full_name accepted_user_name,
                   accepted.email accepted_user_email,
                   completed.full_name onboarding_completed_by_name,
                   (
                       SELECT edl.id
                       FROM email_delivery_log edl
                       WHERE edl.related_invite_id = bi.id
                         AND edl.email_type IN ('business_invite', 'prospect_trial_invite')
                       ORDER BY edl.created_at DESC, edl.id DESC
                       LIMIT 1
                   ) AS last_invite_email_id,
                   (
                       SELECT edl.status
                       FROM email_delivery_log edl
                       WHERE edl.related_invite_id = bi.id
                         AND edl.email_type IN ('business_invite', 'prospect_trial_invite')
                       ORDER BY edl.created_at DESC, edl.id DESC
                       LIMIT 1
                   ) AS last_invite_email_status,
                   (
                       SELECT edl.email_type
                       FROM email_delivery_log edl
                       WHERE edl.related_invite_id = bi.id
                         AND edl.email_type IN ('business_invite', 'prospect_trial_invite')
                       ORDER BY edl.created_at DESC, edl.id DESC
                       LIMIT 1
                   ) AS last_invite_email_type,
                   (
                       SELECT edl.created_at
                       FROM email_delivery_log edl
                       WHERE edl.related_invite_id = bi.id
                         AND edl.email_type IN ('business_invite', 'prospect_trial_invite')
                       ORDER BY edl.created_at DESC, edl.id DESC
                       LIMIT 1
                   ) AS last_invite_email_sent_at,
                   (
                       SELECT edl.opened_at
                       FROM email_delivery_log edl
                       WHERE edl.related_invite_id = bi.id
                         AND edl.email_type IN ('business_invite', 'prospect_trial_invite')
                       ORDER BY edl.created_at DESC, edl.id DESC
                       LIMIT 1
                   ) AS last_invite_email_opened_at,
                   (
                       SELECT edl.open_count
                       FROM email_delivery_log edl
                       WHERE edl.related_invite_id = bi.id
                         AND edl.email_type IN ('business_invite', 'prospect_trial_invite')
                       ORDER BY edl.created_at DESC, edl.id DESC
                       LIMIT 1
                   ) AS last_invite_email_open_count,
                   (
                       SELECT edl.clicked_at
                       FROM email_delivery_log edl
                       WHERE edl.related_invite_id = bi.id
                         AND edl.email_type IN ('business_invite', 'prospect_trial_invite')
                       ORDER BY edl.created_at DESC, edl.id DESC
                       LIMIT 1
                   ) AS last_invite_email_clicked_at,
                   (
                       SELECT edl.click_count
                       FROM email_delivery_log edl
                       WHERE edl.related_invite_id = bi.id
                         AND edl.email_type IN ('business_invite', 'prospect_trial_invite')
                       ORDER BY edl.created_at DESC, edl.id DESC
                       LIMIT 1
                   ) AS last_invite_email_click_count,
                   (
                       SELECT edl.id
                       FROM email_delivery_log edl
                       WHERE edl.related_invite_id = bi.id
                         AND edl.email_type = 'prospect_trial_followup'
                       ORDER BY edl.created_at DESC, edl.id DESC
                       LIMIT 1
                   ) AS followup_email_id,
                   (
                       SELECT edl.status
                       FROM email_delivery_log edl
                       WHERE edl.related_invite_id = bi.id
                         AND edl.email_type = 'prospect_trial_followup'
                       ORDER BY edl.created_at DESC, edl.id DESC
                       LIMIT 1
                   ) AS followup_email_status,
                   (
                       SELECT edl.created_at
                       FROM email_delivery_log edl
                       WHERE edl.related_invite_id = bi.id
                         AND edl.email_type = 'prospect_trial_followup'
                       ORDER BY edl.created_at DESC, edl.id DESC
                       LIMIT 1
                   ) AS followup_email_sent_at
               FROM clients c
               LEFT JOIN business_invites bi ON bi.id = (
                   SELECT bi2.id
                   FROM business_invites bi2
                   WHERE bi2.client_id = c.id
                   ORDER BY bi2.created_at DESC, bi2.id DESC
                   LIMIT 1
               )
               LEFT JOIN users creator ON creator.id = bi.created_by_user_id
               LEFT JOIN users accepted ON accepted.id = bi.accepted_user_id
               LEFT JOIN users completed ON completed.id = c.onboarding_completed_by_user_id
               WHERE COALESCE(c.record_status,'active')='prospect'
               ORDER BY c.created_at DESC, c.business_name"""
        ).fetchall()
        archived_clients = conn.execute(
            """SELECT
                   c.*,
                   (
                       SELECT edl.id
                       FROM email_delivery_log edl
                       WHERE edl.client_id = c.id
                       ORDER BY edl.created_at DESC, edl.id DESC
                       LIMIT 1
                   ) AS last_email_id,
                   (
                       SELECT edl.email_type
                       FROM email_delivery_log edl
                       WHERE edl.client_id = c.id
                       ORDER BY edl.created_at DESC, edl.id DESC
                       LIMIT 1
                   ) AS last_email_type,
                   (
                       SELECT edl.status
                       FROM email_delivery_log edl
                       WHERE edl.client_id = c.id
                       ORDER BY edl.created_at DESC, edl.id DESC
                       LIMIT 1
                   ) AS last_email_status,
                   (
                       SELECT edl.created_at
                       FROM email_delivery_log edl
                       WHERE edl.client_id = c.id
                       ORDER BY edl.created_at DESC, edl.id DESC
                       LIMIT 1
                   ) AS last_email_sent_at,
                   (
                       SELECT edl.recipient_email
                       FROM email_delivery_log edl
                       WHERE edl.client_id = c.id
                       ORDER BY edl.created_at DESC, edl.id DESC
                       LIMIT 1
                   ) AS last_email_recipient
               FROM clients c
               WHERE COALESCE(c.record_status,'active')='archived'
               ORDER BY COALESCE(c.archived_at, c.updated_at, c.created_at) DESC, c.business_name"""
        ).fetchall()
    prospect_clients = [dict(row) for row in prospect_clients]
    for row in prospect_clients:
        row['pipeline_stage'] = prospect_pipeline_stage(row)
        row['email_attention'] = prospect_email_attention_state(row)
    prospect_stage_counts = summarize_prospect_pipeline(prospect_clients)
    email_logs = recent_email_activity(visible_client_ids(user, include_non_active=True), limit=40)
    return render_template(
        'client_users.html',
        clients=active_clients,
        prospect_clients=prospect_clients,
        archived_clients=archived_clients,
        prospect_stage_counts=prospect_stage_counts,
        users=users,
        invites=invites,
        build_invite_link=build_invite_link,
        app_base_url=configured_base_url(),
        email_logs=email_logs,
        business_categories=business_categories(),
        subscription_status_labels=subscription_status_label_map(),
    )


@app.route('/client-logins/email-preview/<int:email_id>')
@admin_required
def client_user_email_preview(email_id: int):
    user = current_user()
    with get_conn() as conn:
        row = conn.execute(
            """SELECT edl.*, c.business_name, u.full_name created_by_name
               FROM email_delivery_log edl
               LEFT JOIN clients c ON c.id = edl.client_id
               LEFT JOIN users u ON u.id = edl.created_by_user_id
               WHERE edl.id=?""",
            (email_id,)
        ).fetchone()
        if row:
            if row['related_invite_id']:
                related_email_rows = conn.execute(
                    """SELECT id, email_type, recipient_email, status, created_at, subject
                       FROM email_delivery_log
                       WHERE related_invite_id=?
                       ORDER BY created_at DESC, id DESC
                       LIMIT 20""",
                    (row['related_invite_id'],)
                ).fetchall()
                history_scope_label = 'Invite thread history'
            elif row['client_id']:
                related_email_rows = conn.execute(
                    """SELECT id, email_type, recipient_email, status, created_at, subject
                       FROM email_delivery_log
                       WHERE client_id=?
                       ORDER BY created_at DESC, id DESC
                       LIMIT 20""",
                    (row['client_id'],)
                ).fetchall()
                history_scope_label = 'Business email history'
            else:
                related_email_rows = []
                history_scope_label = 'Related history'
    if not row:
        abort(404)
    if user['role'] != 'admin' and row['client_id'] is not None and row['client_id'] not in visible_client_ids(user, include_non_active=True):
        abort(403)
    preview_row = dict(row)
    preview_row['body_html'] = email_preview_html(row['body_html'] or '')
    return render_template('email_preview.html', email_row=preview_row, related_email_rows=related_email_rows, history_scope_label=history_scope_label)


@app.route('/email/open/<tracking_token>.gif')
def email_open_tracking(tracking_token: str):
    record_email_open_event(tracking_token)
    return Response(TRACKING_PIXEL_GIF, mimetype='image/gif', headers={'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0'})


@app.route('/email/click/<tracking_token>')
def email_click_tracking(tracking_token: str):
    target = (request.args.get('target') or '').strip()
    parsed = urlparse(target)
    if not target or parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        return redirect(public_app_url('/main-portal'))
    record_email_click_event(tracking_token)
    return redirect(target)


@app.route('/email-settings', methods=['GET', 'POST'])
@admin_required
def email_settings():
    ensure_app_settings_table()
    ensure_email_settings_profile_table()
    user = current_user()
    if request.method == 'POST':
        action = request.form.get('action', 'save_settings').strip().lower()
        current_profile = load_email_settings_profile()
        smtp_email_input = request.form.get('smtp_email', '').strip().lower()
        smtp_host_input = request.form.get('smtp_host', '').strip()
        smtp_port_input = request.form.get('smtp_port', '').strip()
        smtp_username_input = request.form.get('smtp_username', '').strip()
        sender_name_input = request.form.get('sender_name', '').strip()
        app_base_url_input = request.form.get('app_base_url', '').strip().rstrip('/')
        password = request.form.get('smtp_password', '').strip()

        if action == 'send_test_email':
            smtp_email = smtp_email_input or (current_profile.get('smtp_email') or '').strip().lower()
            smtp_host = smtp_host_input or (current_profile.get('smtp_host') or '').strip() or 'smtp.gmail.com'
            smtp_port = smtp_port_input or (current_profile.get('smtp_port') or '').strip() or '587'
            smtp_username = smtp_username_input or (current_profile.get('smtp_username') or '').strip() or smtp_email
            sender_name = sender_name_input or (current_profile.get('smtp_sender_name') or '').strip() or APP_NAME
            app_base_url = app_base_url_input or (current_profile.get('app_base_url') or '').strip().rstrip('/')
        else:
            smtp_email = smtp_email_input
            smtp_host = smtp_host_input or 'smtp.gmail.com'
            smtp_port = smtp_port_input or '587'
            smtp_username = smtp_username_input or smtp_email
            sender_name = sender_name_input or APP_NAME
            app_base_url = app_base_url_input

        runtime_values = {
            'smtp_email': smtp_email,
            'smtp_host': smtp_host,
            'smtp_port': smtp_port,
            'smtp_username': smtp_username,
            'smtp_sender_name': sender_name,
            'app_base_url': app_base_url,
        }
        set_setting('smtp_email', smtp_email)
        set_setting('smtp_host', smtp_host)
        set_setting('smtp_port', smtp_port)
        set_setting('smtp_username', smtp_username)
        set_setting('smtp_sender_name', sender_name)
        set_setting('app_base_url', app_base_url)
        if password:
            enc = encrypt_secret(password)
            set_setting('smtp_password_enc', enc)
            runtime_values['smtp_password_enc'] = enc
        else:
            existing_enc = current_profile.get('smtp_password_enc') or get_setting('smtp_password_enc') or load_email_runtime_config().get('smtp_password_enc', '')
            runtime_values['smtp_password_enc'] = existing_enc
        save_email_settings_profile(runtime_values, user['id'] if user else None)
        save_email_runtime_config(runtime_values)

        if action == 'send_test_email':
            test_email = request.form.get('test_email', '').strip().lower()
            if not test_email:
                flash('Enter a test email address.', 'danger')
            else:
                try:
                    cfg = smtp_config()
                    if cfg.get('password_unreadable'):
                        raise RuntimeError('Saved SMTP password must be entered again once after the security-key update.')
                    if not cfg['sender_email'] or not cfg['smtp_username'] or not cfg['smtp_password']:
                        raise RuntimeError('SMTP not configured')
                    msg = EmailMessage()
                    msg['Subject'] = f'{APP_NAME} test email'
                    msg['From'] = f"{cfg['sender_name']} <{cfg['sender_email']}>"
                    msg['To'] = test_email
                    msg.set_content(f'This is a test email from {APP_NAME}.')
                    with smtplib.SMTP(cfg['smtp_host'], cfg['smtp_port']) as s:
                        s.ehlo()
                        s.starttls()
                        s.ehlo()
                        s.login(cfg['smtp_username'], cfg['smtp_password'])
                        s.send_message(msg)
                    record_email_settings_test_result('success', test_email, '')
                    flash('Test email sent.', 'success')
                except Exception as e:
                    record_email_settings_test_result('failed', test_email, str(e))
                    flash(f'Test email failed: {str(e)[:200]}', 'danger')
        else:
            flash('Email settings saved.', 'success')
        return redirect(url_for('email_settings'))

    profile = load_email_settings_profile()
    smtp_email = profile.get('smtp_email') or ''
    smtp_host = profile.get('smtp_host') or 'smtp.gmail.com'
    smtp_port = profile.get('smtp_port') or '587'
    smtp_username = profile.get('smtp_username') or smtp_email
    sender_name = profile.get('smtp_sender_name') or APP_NAME
    app_base_url = profile.get('app_base_url') or ''
    password_configured = bool(profile.get('smtp_password_enc'))
    with get_conn() as conn:
        failures = conn.execute("SELECT bi.*, c.business_name FROM business_invites bi JOIN clients c ON c.id=bi.client_id WHERE bi.status='failed' ORDER BY bi.created_at DESC LIMIT 20").fetchall()
    return render_template(
        'email_settings.html',
        smtp_email=smtp_email,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_username=smtp_username,
        sender_name=sender_name,
        app_base_url=app_base_url,
        password_configured=password_configured,
        settings_profile=profile,
        failures=failures,
    )


@app.route('/ai-guide-settings', methods=['GET', 'POST'])
@admin_required
def ai_guide_settings():
    if not ai_guide_visible():
        abort(404)
    ensure_ai_assistant_profile_table()
    user = current_user()
    profile = load_ai_assistant_profile()
    if request.method == 'POST':
        action = request.form.get('action', 'save_settings').strip().lower()
        enabled = 1 if request.form.get('enabled') == 'on' else 0
        model = request.form.get('model', '').strip() or 'gpt-5'
        assistant_label = request.form.get('assistant_label', '').strip() or 'LedgerFlow Guide AI'
        system_prompt = request.form.get('system_prompt', '').strip()
        api_key = request.form.get('api_key', '').strip()
        values = {
            'provider': 'openai',
            'enabled': enabled,
            'model': model,
            'assistant_label': assistant_label,
            'system_prompt': system_prompt,
            'api_key_enc': encrypt_secret(api_key) if api_key else profile.get('api_key_enc', ''),
        }
        save_ai_assistant_profile(values, user['id'] if user else None)
        if action == 'test_ai':
            try:
                snapshot = {
                    'role': 'administrator',
                    'person_name': user['full_name'],
                    'business_name': '',
                    'page_label': 'AI Guide Settings',
                    'context_label': 'Currently on AI Guide Settings.',
                    'topics': admin_assistant_topics(None, 'cpa'),
                }
                matched = assistant_match_topic('administrator dashboard', snapshot['topics'])
                call_openai_assistant('Give me a short LedgerFlow greeting and the best next administrator action.', snapshot, matched)
                record_ai_assistant_test_result('success', '')
                flash('AI Guide test succeeded.', 'success')
            except Exception as exc:
                record_ai_assistant_test_result('failed', str(exc))
                flash(f'AI Guide test failed: {str(exc)[:220]}', 'danger')
        else:
            flash('AI Guide settings saved.', 'success')
        return redirect(url_for('ai_guide_settings'))

    config = ai_assistant_config()
    return render_template(
        'ai_guide_settings.html',
        ai_profile=profile,
        ai_config=config,
        api_key_configured=bool(profile.get('api_key_enc')),
    )


@app.route('/assistant/respond', methods=['POST'])
def assistant_respond():
    if not ai_guide_visible():
        return jsonify({'ok': False, 'error': 'AI Guide is not enabled for this portal.'}), 404
    user = current_user()
    worker = current_worker()
    if not user and not worker:
        return jsonify({'ok': False, 'error': 'Authentication required.'}), 403
    data = request.get_json(silent=True) or {}
    question = (data.get('question') or '').strip()
    if not question:
        return jsonify({'ok': False, 'error': 'Enter a question for the AI Guide.'}), 400
    snapshot = assistant_runtime_snapshot(user, worker, active_client_for_request(user), current_mode_for_request(user))
    matched = assistant_match_topic(question, snapshot.get('topics', []))
    try:
        reply = call_openai_assistant(question, snapshot, matched)
        if matched:
            reply['link_label'] = matched.get('link_label', '')
            reply['link_url'] = matched.get('link_url', '')
        record_ai_assistant_test_result('success', '')
        return jsonify({'ok': True, 'reply': reply})
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)[:260]}), 503


@app.route('/business-invite/<token>', methods=['GET', 'POST'])
def business_invite(token):
    if session.get('user_id') or session.get('worker_id'):
        session.clear()
    with get_conn() as conn:
        invite = conn.execute(
            '''SELECT bi.*, c.business_name, c.contact_name, c.email client_email, c.record_status, c.service_level,
                      c.subscription_plan_code, c.preferred_language, c.trial_offer_days, c.trial_started_at, c.trial_ends_at
               FROM business_invites bi
               JOIN clients c ON c.id=bi.client_id
               WHERE bi.token=?''',
            (token,)
        ).fetchone()
        if not invite:
            abort(404)
        invite_language = seed_guest_language(invite['preferred_language'])
        expires_at = datetime.strptime(invite['expires_at'], '%Y-%m-%d %H:%M:%S')
        if invite['status'] != 'accepted' and datetime.utcnow() > expires_at:
            conn.execute('UPDATE business_invites SET status="expired" WHERE id=?', (invite['id'],))
            conn.commit()
            invite = conn.execute(
                '''SELECT bi.*, c.business_name, c.contact_name, c.email client_email, c.record_status, c.service_level,
                          c.subscription_plan_code, c.preferred_language, c.trial_offer_days, c.trial_started_at, c.trial_ends_at
                   FROM business_invites bi
                   JOIN clients c ON c.id=bi.client_id
                   WHERE bi.token=?''',
                (token,)
            ).fetchone()
            invite_language = seed_guest_language(invite['preferred_language'])
        if request.method == 'POST' and invite['status'] in ('pending','sent','failed'):
            email = request.form.get('email', '').strip().lower()
            full_name = request.form.get('full_name', '').strip()
            password = request.form.get('password', '').strip()
            confirm_password = request.form.get('confirm_password', '').strip()
            existing = conn.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone()
            if not full_name:
                flash(translate_text('Full name is required.', invite_language), 'error')
            elif not email:
                flash(translate_text('Email is required.', invite_language), 'error')
            elif existing:
                flash(translate_text('That email already has an account. Sign in instead, or use Forgot Password if needed.', invite_language), 'error')
            elif len(password) < 8:
                flash(translate_text('Password must be at least 8 characters.', invite_language), 'error')
            elif password != confirm_password:
                flash(translate_text('Passwords do not match.', invite_language), 'error')
            else:
                conn.execute(
                    'INSERT INTO users (email, password_hash, full_name, role, client_id, preferred_language) VALUES (?,?,?,?,?,?)',
                    (
                        email,
                        generate_password_hash(password),
                        full_name,
                        'client',
                        invite['client_id'],
                        normalize_language(invite_language or (invite['preferred_language'] or '') or 'en'),
                    )
                )
                new_user = conn.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone()
                client_row = conn.execute('SELECT * FROM clients WHERE id=?', (invite['client_id'],)).fetchone()
                contact_name = (client_row['contact_name'] if client_row else '') or ''
                client_email = (client_row['email'] if client_row else '') or ''
                login_created_at = now_iso()
                is_trial_claim = normalize_invite_kind(invite['invite_kind']) == 'prospect_trial'
                trial_days = int(invite['trial_days'] or client_row['trial_offer_days'] or default_trial_offer_days())
                if not contact_name.strip() or not client_email.strip():
                    conn.execute(
                        '''UPDATE clients
                           SET contact_name=CASE WHEN COALESCE(contact_name, "")="" THEN ? ELSE contact_name END,
                               email=CASE WHEN COALESCE(email, "")="" THEN ? ELSE email END,
                               updated_at=?,
                               updated_by_user_id=?
                           WHERE id=?''',
                        (full_name, email, login_created_at, new_user['id'], invite['client_id'])
                    )
                if is_trial_claim:
                    trial_started_at_value = client_row['trial_started_at'] or login_created_at
                    trial_started_at_value, trial_ends_at_value = trial_date_window(trial_started_at_value, trial_days)
                    conn.execute(
                        '''UPDATE clients
                           SET trial_offer_days=CASE WHEN COALESCE(trial_offer_days, 0)=0 THEN ? ELSE trial_offer_days END,
                               trial_started_at=CASE WHEN COALESCE(trial_started_at,'')='' THEN ? ELSE trial_started_at END,
                               trial_ends_at=CASE WHEN COALESCE(trial_ends_at,'')='' THEN ? ELSE trial_ends_at END,
                               subscription_next_billing_date=CASE WHEN COALESCE(subscription_next_billing_date,'')='' THEN ? ELSE subscription_next_billing_date END,
                               updated_at=?,
                               updated_by_user_id=?
                           WHERE id=?''',
                        (trial_days, trial_started_at_value, trial_ends_at_value, trial_ends_at_value[:10], login_created_at, new_user['id'], invite['client_id'])
                    )
                onboarding_needed = not client_onboarding_is_complete(conn, client_row)
                if onboarding_needed:
                    conn.execute(
                        '''UPDATE clients
                           SET onboarding_status='in_progress',
                               onboarding_started_at=CASE WHEN COALESCE(onboarding_started_at,'')='' THEN ? ELSE onboarding_started_at END,
                               onboarding_completed_at='',
                               onboarding_completed_by_user_id=NULL,
                               updated_at=?,
                               updated_by_user_id=?
                           WHERE id=?''',
                        (login_created_at, login_created_at, new_user['id'], invite['client_id'])
                    )
                log_client_profile_history(
                    conn,
                    client_id=invite['client_id'],
                    action='business_login_created',
                    changed_by_user_id=new_user['id'],
                    detail='Business login created from invite.',
                )
                log_account_activity(
                    conn,
                    client_id=invite['client_id'],
                    account_type='trial_business_login' if is_trial_claim else 'business_login',
                    account_email=email,
                    account_name=full_name,
                    created_by_user_id=invite['created_by_user_id'],
                    status='claimed_trial' if is_trial_claim else 'created',
                    detail='Business login created from invite.',
                )
                conn.execute('UPDATE business_invites SET status="accepted", used_at=CURRENT_TIMESTAMP, accepted_user_id=? WHERE id=?', (new_user['id'], invite['id']))
                conn.commit()
                session.clear()
                session['user_id'] = new_user['id']
                session['preferred_language'] = normalize_language(invite_language or (invite['preferred_language'] or '') or 'en')
                if is_trial_claim and smtp_email_ready():
                    trial_end_row = conn.execute(
                        'SELECT trial_ends_at FROM clients WHERE id=?',
                        (invite['client_id'],),
                    ).fetchone()
                    trial_end_date = (trial_end_row['trial_ends_at'] if trial_end_row else '') or ''
                    try:
                        trial_claim_payload = send_business_trial_claimed_email(
                            email,
                            full_name,
                            invite['business_name'],
                            trial_days=trial_days,
                            trial_end_date=trial_end_date,
                        )
                        log_email_delivery(
                            client_id=invite['client_id'],
                            email_type=trial_claim_payload['email_type'],
                            recipient_email=email,
                            recipient_name=full_name,
                            subject=trial_claim_payload['subject'],
                            body_text=trial_claim_payload['body_text'],
                            body_html=trial_claim_payload['body_html'],
                            status='sent',
                            created_by_user_id=invite['created_by_user_id'],
                            related_invite_id=invite['id'],
                            related_user_id=new_user['id'],
                        )
                    except Exception as e:
                        log_email_delivery(
                            client_id=invite['client_id'],
                            email_type='business_trial_claimed',
                            recipient_email=email,
                            recipient_name=full_name,
                            subject=f'Your LedgerFlow trial is ready for {invite["business_name"]}',
                            status='failed',
                            error_message=str(e)[:500],
                            created_by_user_id=invite['created_by_user_id'],
                            related_invite_id=invite['id'],
                            related_user_id=new_user['id'],
                        )
                    admin_user_id = preferred_admin_notification_user_id(conn, invite['client_id'], invite['created_by_user_id'])
                    for admin_row in admin_notification_recipients(conn, admin_user_id):
                        try:
                            admin_payload = send_admin_trial_claimed_email(
                                admin_row['email'],
                                admin_row['full_name'],
                                invite['business_name'],
                                claimed_by_name=full_name,
                                claimed_by_email=email,
                                trial_days=trial_days,
                                claimed_at=login_created_at,
                            )
                            log_email_delivery(
                                client_id=invite['client_id'],
                                email_type=admin_payload['email_type'],
                                recipient_email=admin_row['email'],
                                recipient_name=admin_row['full_name'],
                                subject=admin_payload['subject'],
                                body_text=admin_payload['body_text'],
                                body_html=admin_payload['body_html'],
                                status='sent',
                                created_by_user_id=invite['created_by_user_id'],
                                related_invite_id=invite['id'],
                                related_user_id=new_user['id'],
                            )
                        except Exception as e:
                            log_email_delivery(
                                client_id=invite['client_id'],
                                email_type='trial_claimed_notification',
                                recipient_email=admin_row['email'],
                                recipient_name=admin_row['full_name'],
                                subject=f'Trial claimed: {invite["business_name"]}',
                                status='failed',
                                error_message=str(e)[:500],
                                created_by_user_id=invite['created_by_user_id'],
                                related_invite_id=invite['id'],
                                related_user_id=new_user['id'],
                            )
                if onboarding_needed:
                    if is_trial_claim:
                        flash(translate_text('Trial claimed. Start in the Welcome Center, review the guided overview, and finish the quick setup when you are ready.', invite_language), 'success')
                        return redirect(url_for('welcome_center'))
                    flash(translate_text('Business login created. Complete setup to unlock your full LedgerFlow workspace.', invite_language), 'success')
                    return redirect(url_for('business_onboarding'))
                if is_trial_claim:
                    flash(translate_text('Trial claimed. Your LedgerFlow workspace is ready to explore.', invite_language), 'success')
                    return redirect(url_for('welcome_center'))
                welcome_sent = False
                welcome_error = ''
                if smtp_email_ready():
                    try:
                        send_welcome_email(
                            email,
                            full_name,
                            'business',
                            login_path='/main-portal',
                            business_name=(invite['business_name'] if invite else '')
                        )
                        welcome_sent = True
                    except Exception as e:
                        welcome_error = str(e)[:200]
                if welcome_sent:
                    flash(translate_text('Business login created. Welcome email sent. Sign in below.', invite_language), 'success')
                elif smtp_email_ready():
                    flash(translate_text('Business login created, but welcome email failed: {error_message}', invite_language, error_message=welcome_error), 'error')
                else:
                    flash(translate_text('Business login created. Sign in below.', invite_language), 'success')
                return redirect(url_for('dashboard'))
    trial_offer_days = int(invite['trial_days'] or invite['trial_offer_days'] or 0)
    return render_template(
        'business_invite.html',
        invite=invite,
        is_trial_invite=normalize_invite_kind(invite['invite_kind']) == 'prospect_trial' and trial_offer_days > 0,
        trial_offer_days=trial_offer_days or default_trial_offer_days(),
        subscription_tiers=subscription_tier_view_data(),
        invite_kind_label=invite_kind_label(invite['invite_kind']),
    )


@app.route('/business-rejoin/<token>', methods=['GET', 'POST'])
def business_rejoin(token):
    if session.get('user_id') or session.get('worker_id'):
        session.clear()
    with get_conn() as conn:
        invite = conn.execute(
            'SELECT bi.*, c.business_name, c.record_status, c.onboarding_status, c.preferred_language FROM business_invites bi JOIN clients c ON c.id=bi.client_id WHERE bi.token=?',
            (token,)
        ).fetchone()
        if not invite:
            abort(404)
        invite_language = seed_guest_language(invite['preferred_language'])
        expires_at = datetime.strptime(invite['expires_at'], '%Y-%m-%d %H:%M:%S')
        if invite['status'] != 'accepted' and datetime.utcnow() > expires_at:
            conn.execute('UPDATE business_invites SET status="expired" WHERE id=?', (invite['id'],))
            conn.commit()
            invite = conn.execute(
                'SELECT bi.*, c.business_name, c.record_status, c.onboarding_status, c.preferred_language FROM business_invites bi JOIN clients c ON c.id=bi.client_id WHERE bi.token=?',
                (token,)
            ).fetchone()
            invite_language = seed_guest_language(invite['preferred_language'])
        existing_login = conn.execute(
            'SELECT id, email, full_name FROM users WHERE role="client" AND client_id=? ORDER BY id DESC LIMIT 1',
            (invite['client_id'],)
        ).fetchone()
        if request.method == 'POST' and invite['status'] in ('pending', 'sent', 'failed'):
            now_value = now_iso()
            conn.execute(
                '''UPDATE clients
                   SET record_status='active',
                       archive_reason='',
                       archived_at='',
                       archived_by_user_id=NULL,
                       reactivated_at=?,
                       updated_at=?,
                       updated_by_user_id=?
                   WHERE id=?''',
                (now_value, now_value, existing_login['id'] if existing_login else None, invite['client_id'])
            )
            accepted_user_id = existing_login['id'] if existing_login else None
            conn.execute(
                'UPDATE business_invites SET status="accepted", used_at=CURRENT_TIMESTAMP, accepted_user_id=? WHERE id=?',
                (accepted_user_id, invite['id'])
            )
            log_client_profile_history(
                conn,
                client_id=invite['client_id'],
                action='rejoin_restored',
                changed_by_user_id=accepted_user_id,
                detail='Archived business restored from rejoin link.',
            )
            conn.commit()
            if existing_login:
                flash(translate_text('Your LedgerFlow workspace has been restored. Sign in to continue.', invite_language), 'success')
                return redirect(url_for('main_portal'))
            flash(translate_text('Workspace restored. Create your business login to continue.', invite_language), 'success')
            return redirect(url_for('business_invite', token=token))
    return render_template('business_rejoin.html', invite=invite, existing_login=existing_login)


@app.route('/business-onboarding', methods=['GET', 'POST'])
@login_required
def business_onboarding():
    user = current_user()
    if user['role'] != 'client':
        return redirect(url_for('cpa_dashboard'))
    client_id = user['client_id']
    with get_conn() as conn:
        client = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
        if not client:
            abort(404)
        default_method = conn.execute(
            '''SELECT *
               FROM business_payment_methods
               WHERE client_id=?
               ORDER BY is_default DESC, updated_at DESC, id DESC''',
            (client_id,)
        ).fetchone()
        trial_offer_days = int(client['trial_offer_days'] or 0)
        trial_ends_at = (client['trial_ends_at'] or '').strip()
        trial_billing_start = trial_ends_at[:10] if trial_offer_days and trial_ends_at else ''
        trial_payment_optional = trial_offer_days > 0
        if request.method == 'POST':
            selected_language = normalize_language(
                request.form.get('preferred_language')
                or session.get('preferred_language')
                or user['preferred_language']
                or client['preferred_language']
            )
            session['preferred_language'] = selected_language
            business_name = request.form.get('business_name', '').strip()
            business_structure = request.form.get('business_type', '').strip()
            business_category = normalize_business_category(request.form.get('business_category', ''))
            business_specialty = request.form.get('business_specialty', '').strip()[:120]
            owner_contacts = request.form.get('owner_contacts', '').strip()[:1200]
            job_scope_summary = request.form.get('job_scope_summary', '').strip()[:2000]
            contact_name = request.form.get('contact_name', '').strip()
            phone = request.form.get('phone', '').strip()
            email = request.form.get('email', '').strip().lower()
            address = request.form.get('address', '').strip()
            ein = request.form.get('ein', '').strip()
            service_level = normalize_service_level(request.form.get('service_level', default_service_level()))
            billing_notes = request.form.get('billing_notes', '').strip()[:500]
            start_date_raw = request.form.get('subscription_start_date', '').strip()
            start_date = parse_date(start_date_raw)
            submitted_payment_fields = [
                request.form.get('label', '').strip(),
                request.form.get('brand_name', '').strip(),
                request.form.get('holder_name', '').strip(),
                request.form.get('card_number', '').strip(),
                request.form.get('account_last4', '').strip(),
                request.form.get('expiry_display', '').strip(),
                request.form.get('routing_number', '').strip(),
                request.form.get('account_number', '').strip(),
                request.form.get('confirm_account_number', '').strip(),
                request.form.get('details_note', '').strip(),
            ]
            submitted_payment_method = any(submitted_payment_fields)
            trial_billing_opt_in = request.form.get('add_billing_now') in {'1', 'on', 'true', 'yes'}
            errors: list[str] = []
            if not business_name:
                errors.append('Business name is required.')
            if not contact_name:
                errors.append('Primary contact name is required.')
            if not email:
                errors.append('Business email is required.')
            elif '@' not in email or '.' not in email.split('@')[-1]:
                errors.append('Enter a valid business email address.')
            if not phone:
                errors.append('Business phone is required.')
            if not address:
                errors.append('Business address is required.')
            if not start_date:
                errors.append('Select a subscription start date.')
            cleaned_method = None
            if (not trial_payment_optional) or (trial_billing_opt_in and submitted_payment_method):
                cleaned_method, payment_errors = validate_payment_method_form(request.form, existing=default_method)
                errors.extend(payment_errors)
            if errors:
                for error in errors:
                    flash(error, 'error')
            else:
                subscription_amount_decimal = suggested_payment_amount(service_level, 'monthly_platform_fee') or Decimal('0.00')
                started_at, canceled_at, paused_at = subscription_status_timestamps('active', client)
                next_billing_date = start_date.isoformat()
                setup_completed_at = now_iso()
                autopay_enabled = 0
                if not trial_payment_optional:
                    autopay_enabled = 1 if request.form.get('subscription_autopay_enabled') in {'1', 'on', 'true', 'yes'} else 0
                conn.execute(
                    '''UPDATE clients
                       SET business_name=?, business_type=?, business_category=?, business_specialty=?, preferred_language=?, service_level=?, contact_name=?, phone=?, email=?, address=?, ein=?,
                           subscription_plan_code=?, subscription_status='active', subscription_amount=?, subscription_interval='monthly',
                           subscription_autopay_enabled=?, subscription_next_billing_date=?, subscription_started_at=?,
                           subscription_canceled_at=?, subscription_paused_at=?, billing_notes=?, onboarding_status='completed',
                           record_status='active', archive_reason='', archived_at='', archived_by_user_id=NULL,
                           onboarding_started_at=CASE WHEN COALESCE(onboarding_started_at,'')='' THEN ? ELSE onboarding_started_at END,
                           onboarding_completed_at=?, onboarding_completed_by_user_id=?, updated_at=?, updated_by_user_id=?
                       WHERE id=?''',
                    (
                        business_name,
                        business_structure,
                        business_category,
                        business_specialty,
                        selected_language,
                        service_level,
                        contact_name,
                        phone,
                        email,
                        address,
                        ein,
                        service_level_plan_code(service_level),
                        float(subscription_amount_decimal),
                        autopay_enabled,
                        next_billing_date,
                        started_at,
                        canceled_at,
                        paused_at,
                        billing_notes,
                        setup_completed_at,
                        setup_completed_at,
                        user['id'],
                        setup_completed_at,
                        user['id'],
                        client_id,
                    )
                )
                conn.execute('UPDATE clients SET owner_contacts=?, job_scope_summary=? WHERE id=?', (owner_contacts, job_scope_summary, client_id))
                if cleaned_method:
                    if cleaned_method['is_default'] != 1:
                        cleaned_method['is_default'] = 1
                    if default_method:
                        if cleaned_method['is_default']:
                            conn.execute('UPDATE business_payment_methods SET is_default=0 WHERE client_id=?', (client_id,))
                        if cleaned_method['is_backup']:
                            conn.execute('UPDATE business_payment_methods SET is_backup=0 WHERE client_id=?', (client_id,))
                        conn.execute(
                            '''UPDATE business_payment_methods
                               SET method_type=?, label=?, status=?, is_default=?, is_backup=?, holder_name=?, brand_name=?, account_last4=?, expiry_display=?, account_type=?, card_number_enc=?, routing_number_enc=?, account_number_enc=?, details_note=?, updated_at=?
                               WHERE id=? AND client_id=?''',
                            (
                                cleaned_method['method_type'],
                                cleaned_method['label'],
                                cleaned_method['status'],
                                cleaned_method['is_default'],
                                cleaned_method['is_backup'],
                                cleaned_method['holder_name'],
                                cleaned_method['brand_name'],
                                cleaned_method['account_last4'],
                                cleaned_method['expiry_display'],
                                cleaned_method['account_type'],
                                cleaned_method['card_number_enc'],
                                cleaned_method['routing_number_enc'],
                                cleaned_method['account_number_enc'],
                                cleaned_method['details_note'],
                                datetime.now().isoformat(timespec='seconds'),
                                default_method['id'],
                                client_id,
                            )
                        )
                    else:
                        conn.execute(
                            '''INSERT INTO business_payment_methods (client_id, method_type, label, status, is_default, is_backup, holder_name, brand_name, account_last4, expiry_display, account_type, card_number_enc, routing_number_enc, account_number_enc, details_note, created_by_user_id, updated_at)
                               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                            (
                                client_id,
                                cleaned_method['method_type'],
                                cleaned_method['label'],
                                cleaned_method['status'],
                                cleaned_method['is_default'],
                                cleaned_method['is_backup'],
                                cleaned_method['holder_name'],
                                cleaned_method['brand_name'],
                                cleaned_method['account_last4'],
                                cleaned_method['expiry_display'],
                                cleaned_method['account_type'],
                                cleaned_method['card_number_enc'],
                                cleaned_method['routing_number_enc'],
                                cleaned_method['account_number_enc'],
                                cleaned_method['details_note'],
                                user['id'],
                                datetime.now().isoformat(timespec='seconds'),
                            )
                        )
                sync_client_payment_method_summary(conn, client_id)
                conn.execute(
                    'UPDATE users SET preferred_language=? WHERE id=?',
                    (selected_language, user['id'])
                )
                log_client_profile_history(
                    conn,
                    client_id=client_id,
                    action='onboarding_completed',
                    changed_by_user_id=user['id'],
                    detail='Business setup completed and subscription foundation saved.',
                )
                log_account_activity(
                    conn,
                    client_id=client_id,
                    account_type='subscription_activation',
                    account_email=email,
                    account_name=contact_name,
                    created_by_user_id=user['id'],
                    status='subscription_active',
                    detail=f'Subscription activated on {service_level_label_map().get(service_level, service_level)}.',
                )
                conn.commit()
                welcome_sent = False
                welcome_error = ''
                welcome_payload = None
                admin_notification_user_id = preferred_admin_notification_user_id(conn, client_id)
                if smtp_email_ready():
                    try:
                        welcome_payload = send_welcome_email(
                            email,
                            contact_name,
                            'business',
                            login_path='/main-portal',
                            business_name=business_name
                        )
                        welcome_sent = True
                    except Exception as e:
                        welcome_error = str(e)[:200]
                if welcome_sent and welcome_payload:
                    log_email_delivery(
                        client_id=client_id,
                        email_type=welcome_payload['email_type'],
                        recipient_email=email,
                        recipient_name=contact_name,
                        subject=welcome_payload['subject'],
                        body_text=welcome_payload['body_text'],
                        body_html=welcome_payload['body_html'],
                        status='sent',
                        created_by_user_id=user['id'],
                        related_user_id=user['id'],
                    )
                elif welcome_error:
                    log_email_delivery(
                        client_id=client_id,
                        email_type='business_welcome',
                        recipient_email=email,
                        recipient_name=contact_name,
                        subject='Welcome to LedgerFlow - Business Login',
                        status='failed',
                        error_message=welcome_error,
                        created_by_user_id=user['id'],
                        related_user_id=user['id'],
                    )
                if smtp_email_ready():
                    tier_label = service_level_label_map().get(service_level, service_level)
                    for admin_row in admin_notification_recipients(conn, admin_notification_user_id):
                        try:
                            activation_payload = send_admin_subscription_activation_email(
                                admin_row['email'],
                                admin_row['full_name'],
                                business_name,
                                activated_by_name=contact_name,
                                activated_by_email=email,
                                tier_label=tier_label,
                                monthly_amount=float(subscription_amount_decimal),
                            )
                            log_email_delivery(
                                client_id=client_id,
                                email_type=activation_payload['email_type'],
                                recipient_email=admin_row['email'],
                                recipient_name=admin_row['full_name'],
                                subject=activation_payload['subject'],
                                body_text=activation_payload['body_text'],
                                body_html=activation_payload['body_html'],
                                status='sent',
                                created_by_user_id=user['id'],
                                related_user_id=user['id'],
                            )
                        except Exception as e:
                            log_email_delivery(
                                client_id=client_id,
                                email_type='subscription_activation_notification',
                                recipient_email=admin_row['email'],
                                recipient_name=admin_row['full_name'],
                                subject=f'Subscription activated: {business_name}',
                                status='failed',
                                error_message=str(e)[:500],
                                created_by_user_id=user['id'],
                                related_user_id=user['id'],
                            )
                if welcome_sent:
                    flash('Setup complete. Your LedgerFlow workspace is ready and your welcome email has been sent.', 'success')
                elif smtp_email_ready():
                    flash(f'Setup complete, but the welcome email failed: {welcome_error}', 'error')
                else:
                    flash('Setup complete. Your LedgerFlow workspace is ready.', 'success')
                return redirect(url_for('welcome_center'))
        if (client['onboarding_status'] or 'completed') == 'completed':
            return redirect(url_for('dashboard'))
        suggested_amount = suggested_payment_amount(client['service_level'] or default_service_level(), 'monthly_platform_fee') or Decimal('0.00')
        return render_template(
            'business_onboarding.html',
            client=client,
            suggested_subscription_amount=float(suggested_amount),
            business_structures=business_structures(),
            business_categories=business_categories(),
            service_level_options=service_level_options(),
            service_level_labels=service_level_label_map(),
            payment_method_type_options=payment_method_type_options(),
            default_method=default_method,
            payment_method_type_labels=payment_method_type_label_map(),
            trial_offer_days=trial_offer_days,
            trial_ends_at=trial_ends_at,
            default_subscription_start_date=(request.form.get('subscription_start_date', '').strip() or client['subscription_next_billing_date'] or trial_billing_start or today),
        )


@app.route('/invoices', methods=['GET', 'POST'])
@login_required
def invoices():
    user = current_user()
    client_id = selected_client_id(user, 'post' if request.method == 'POST' else 'get')
    today_iso = date.today().isoformat()
    default_due_date = (date.today() + timedelta(days=14)).isoformat()
    prefill_contact_id = request.values.get('customer_contact_id', type=int)
    with get_conn() as conn:
        client = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
        if not client or not allowed_client(user, client_id):
            abort(403)
        sales_workspace_enabled = premium_sales_access_enabled(client)
        customer_contact_rows = conn.execute(
            '''SELECT *
               FROM customer_contacts
               WHERE client_id=? AND COALESCE(status,'active')='active'
               ORDER BY LOWER(customer_name), id DESC''',
            (client_id,),
        ).fetchall() if sales_workspace_enabled else []
        customer_contact_lookup = {row['id']: row for row in customer_contact_rows}
        prefill_contact = customer_contact_lookup.get(prefill_contact_id) if sales_workspace_enabled else None
        if request.method == 'POST':
            action = request.form.get('action', 'add_invoice').strip()
            if action in {'create_customer_invoice', 'send_customer_invoice', 'send_customer_invoice_reminder', 'mark_customer_invoice_paid', 'send_customer_receipt'} and not sales_workspace_enabled:
                return premium_sales_redirect(client_id)
            if action == 'add_mileage':
                start_point = request.form.get('start_point', '').strip()
                destination = request.form.get('destination', '').strip()
                trip_type = request.form.get('trip_type', 'two_way').strip()
                round_trips = request.form.get('round_trips', type=int) or 1
                round_trips = max(round_trips, 1)
                invoice_id = request.form.get('invoice_id', type=int)
                one_way_miles = request.form.get('one_way_miles', type=float) or 0
                if one_way_miles <= 0 and start_point and destination:
                    one_way_miles = estimate_miles(start_point, destination)
                trip_multiplier = 1 if trip_type == 'one_way' else 2
                total_miles = round(one_way_miles * trip_multiplier * round_trips, 2)
                rate = request.form.get('rate', type=float)
                if rate is None:
                    rate = IRS_MILEAGE_RATE
                total_amount = round(total_miles * rate, 2)
                conn.execute(
                    'INSERT INTO invoice_mileage_entries (client_id, invoice_id, trip_date, start_point, destination, trip_type, round_trips, one_way_miles, total_miles, rate, total_amount, note) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                    (client_id, invoice_id, request.form.get('trip_date', '').strip(), start_point, destination, trip_type, round_trips, one_way_miles, total_miles, rate, total_amount, request.form.get('note', '').strip())
                )
                conn.commit()
                flash('Invoice mileage entry saved.', 'success')
                return redirect(url_for('invoices', client_id=client_id))
            if action == 'create_customer_invoice':
                errors: list[str] = []
                selected_contact = customer_contact_lookup.get(request.form.get('customer_contact_id', type=int))
                selected_contact_id = selected_contact['id'] if selected_contact else None
                customer_name = request.form.get('client_name', '').strip()
                recipient_email = request.form.get('recipient_email', '').strip().lower()
                invoice_date = request.form.get('invoice_date', '').strip() or today_iso
                due_date = request.form.get('due_date', '').strip()
                invoice_title = request.form.get('invoice_title', '').strip() or 'Customer Invoice'
                client_address = request.form.get('client_address', '').strip()
                notes = request.form.get('notes', '').strip()
                customer_phone = request.form.get('customer_phone', '').strip()
                if selected_contact:
                    customer_name = customer_name or (selected_contact['customer_name'] or '').strip()
                    recipient_email = recipient_email or (selected_contact['customer_email'] or '').strip().lower()
                    client_address = client_address or (selected_contact['customer_address'] or '').strip()
                    customer_phone = customer_phone or (selected_contact['customer_phone'] or '').strip()
                payment_link = normalize_payment_link(request.form.get('public_payment_link', '').strip())
                sales_tax_amount = normalize_money_amount(request.form.get('sales_tax_amount', '0') or '0')
                items, item_errors = parse_invoice_line_items(request.form)
                errors.extend(item_errors)
                if not customer_name:
                    errors.append('Customer name is required.')
                if not recipient_email or '@' not in recipient_email:
                    errors.append('A valid recipient email is required.')
                if payment_link is None:
                    errors.append('Online payment link must be a valid http or https URL.')
                if not parse_date(invoice_date):
                    errors.append('Issue date is invalid.')
                if due_date and not parse_date(due_date):
                    errors.append('Due date is invalid.')
                if sales_tax_amount is None or sales_tax_amount < 0:
                    errors.append('Sales tax amount is invalid.')
                subtotal = invoice_subtotal(items) if not item_errors else Decimal('0.00')
                total_amount = (subtotal + (sales_tax_amount or Decimal('0.00'))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                if total_amount <= 0:
                    errors.append('Invoice total must be above zero.')
                if errors:
                    for error in errors:
                        flash(error, 'error')
                    return redirect(url_for('invoices', client_id=client_id))
                next_job = conn.execute('SELECT COALESCE(MAX(job_number),0)+1 n FROM invoices WHERE client_id=?', (client_id,)).fetchone()['n']
                token = generate_invoice_public_token()
                while conn.execute('SELECT 1 FROM invoices WHERE public_invoice_token=? LIMIT 1', (token,)).fetchone():
                    token = generate_invoice_public_token()
                saved_contact_id = upsert_customer_contact(
                    conn,
                    client_id=client_id,
                    customer_name=customer_name,
                    customer_email=recipient_email,
                    customer_phone=customer_phone,
                    customer_address=client_address,
                    customer_notes=notes,
                    created_by_user_id=user['id'],
                )
                customer_contact_id = selected_contact_id or saved_contact_id
                cursor = conn.execute(
                    '''INSERT INTO invoices (
                        client_id, customer_contact_id, job_number, record_kind, invoice_title, client_name, recipient_email, client_address,
                        invoice_total_amount, paid_amount, invoice_date, due_date, invoice_status, public_invoice_token,
                        public_payment_link, notes, income_category, sales_tax_amount, sales_tax_paid
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (
                        client_id,
                        customer_contact_id,
                        next_job,
                        'customer_invoice',
                        invoice_title,
                        customer_name,
                        recipient_email,
                        client_address,
                        float(total_amount),
                        0,
                        invoice_date,
                        due_date,
                        'draft',
                        token,
                        payment_link or '',
                        notes,
                        'service_income',
                        float(sales_tax_amount or Decimal('0.00')),
                        0,
                    )
                )
                invoice_id = cursor.lastrowid
                for item in items:
                    conn.execute(
                        '''INSERT INTO invoice_line_items (invoice_id, sort_order, description, quantity, unit_price, line_total)
                           VALUES (?,?,?,?,?,?)''',
                        (
                            invoice_id,
                            item['sort_order'],
                            item['description'],
                            item['quantity'],
                            item['unit_price'],
                            item['line_total'],
                        )
                    )
                send_now = bool(request.form.get('send_now'))
                if send_now:
                    view_link = public_invoice_url(token)
                    try:
                        email_result = send_customer_invoice_email(
                            to_email=recipient_email,
                            to_name=customer_name,
                            business_name=client['business_name'],
                            invoice_number=next_job,
                            invoice_title=invoice_title,
                            invoice_link=view_link,
                            due_date=due_date,
                            total_amount=float(total_amount),
                            payment_link=payment_link or '',
                        )
                        conn.execute(
                            'UPDATE invoices SET invoice_status=?, sent_at=? WHERE id=?',
                            ('overdue' if due_date and due_date < today_iso else 'sent', now_iso(), invoice_id),
                        )
                        log_email_delivery(
                            client_id=client_id,
                            email_type=email_result['email_type'],
                            recipient_email=recipient_email,
                            recipient_name=customer_name,
                            subject=email_result['subject'],
                            body_text=email_result['body_text'],
                            body_html=email_result['body_html'],
                            status='sent',
                            created_by_user_id=user['id'],
                        )
                        flash('Customer invoice saved and sent.', 'success')
                    except Exception as exc:
                        log_email_delivery(
                            client_id=client_id,
                            email_type='customer_invoice',
                            recipient_email=recipient_email,
                            recipient_name=customer_name,
                            subject=f'Invoice #{next_job} from {client["business_name"]}',
                            status='failed',
                            error_message=str(exc)[:500],
                            created_by_user_id=user['id'],
                        )
                        flash(f'Customer invoice saved, but sending failed: {exc}', 'error')
                else:
                    flash('Customer invoice saved.', 'success')
                conn.commit()
                return redirect(url_for('invoices', client_id=client_id))
            if action == 'send_customer_invoice':
                invoice_id = request.form.get('invoice_id', type=int)
                row = conn.execute(
                    '''SELECT i.*, c.business_name
                       FROM invoices i
                       JOIN clients c ON c.id = i.client_id
                       WHERE i.id=? AND i.client_id=? AND COALESCE(i.record_kind,'income_record')='customer_invoice' ''',
                    (invoice_id, client_id),
                ).fetchone()
                if not row:
                    flash('Customer invoice not found.', 'error')
                    return redirect(url_for('invoices', client_id=client_id))
                if not (row['recipient_email'] or '').strip():
                    flash('Add a recipient email before sending this invoice.', 'error')
                    return redirect(url_for('invoices', client_id=client_id))
                token = ensure_invoice_public_token(conn, row['id'])
                view_link = public_invoice_url(token)
                try:
                    email_result = send_customer_invoice_email(
                        to_email=row['recipient_email'],
                        to_name=row['client_name'],
                        business_name=row['business_name'],
                        invoice_number=row['job_number'] or row['id'],
                        invoice_title=row['invoice_title'] or 'Customer Invoice',
                        invoice_link=view_link,
                        due_date=row['due_date'] or '',
                        total_amount=money(row['invoice_total_amount'] or 0),
                        payment_link=(row['public_payment_link'] or '').strip(),
                    )
                    conn.execute(
                        'UPDATE invoices SET invoice_status=?, sent_at=? WHERE id=?',
                        ('overdue' if (row['due_date'] or '') and (row['due_date'] or '') < today_iso and invoice_balance_due(row) > 0 else 'sent', now_iso(), row['id']),
                    )
                    log_email_delivery(
                        client_id=client_id,
                        email_type=email_result['email_type'],
                        recipient_email=row['recipient_email'],
                        recipient_name=row['client_name'],
                        subject=email_result['subject'],
                        body_text=email_result['body_text'],
                        body_html=email_result['body_html'],
                        status='sent',
                        created_by_user_id=user['id'],
                    )
                    conn.commit()
                    flash('Customer invoice sent.', 'success')
                except Exception as exc:
                    log_email_delivery(
                        client_id=client_id,
                        email_type='customer_invoice',
                        recipient_email=row['recipient_email'],
                        recipient_name=row['client_name'],
                        subject=f'Invoice #{row["job_number"] or row["id"]} from {row["business_name"]}',
                        status='failed',
                        error_message=str(exc)[:500],
                        created_by_user_id=user['id'],
                    )
                    conn.commit()
                    flash(f'Invoice send failed: {exc}', 'error')
                return redirect(url_for('invoices', client_id=client_id))
            if action == 'send_customer_invoice_reminder':
                invoice_id = request.form.get('invoice_id', type=int)
                row = conn.execute(
                    '''SELECT i.*, c.business_name
                       FROM invoices i
                       JOIN clients c ON c.id = i.client_id
                       WHERE i.id=? AND i.client_id=? AND COALESCE(i.record_kind,'income_record')='customer_invoice' ''',
                    (invoice_id, client_id),
                ).fetchone()
                if not row:
                    flash('Customer invoice not found.', 'error')
                    return redirect(url_for('invoices', client_id=client_id))
                token = ensure_invoice_public_token(conn, row['id'])
                view_link = public_invoice_url(token)
                try:
                    email_result = send_customer_invoice_reminder_email(
                        to_email=row['recipient_email'],
                        to_name=row['client_name'],
                        business_name=row['business_name'],
                        invoice_number=row['job_number'] or row['id'],
                        invoice_title=row['invoice_title'] or 'Customer Invoice',
                        invoice_link=view_link,
                        due_date=row['due_date'] or '',
                        balance_due=invoice_balance_due(row),
                        payment_link=(row['public_payment_link'] or '').strip(),
                    )
                    conn.execute(
                        '''UPDATE invoices
                           SET invoice_status=?, last_reminder_at=?, reminder_count=COALESCE(reminder_count,0)+1
                           WHERE id=?''',
                        ('overdue' if (row['due_date'] or '') and (row['due_date'] or '') < today_iso and invoice_balance_due(row) > 0 else 'sent', now_iso(), row['id']),
                    )
                    log_email_delivery(
                        client_id=client_id,
                        email_type=email_result['email_type'],
                        recipient_email=row['recipient_email'],
                        recipient_name=row['client_name'],
                        subject=email_result['subject'],
                        body_text=email_result['body_text'],
                        body_html=email_result['body_html'],
                        status='sent',
                        created_by_user_id=user['id'],
                    )
                    conn.commit()
                    flash('Invoice reminder sent.', 'success')
                except Exception as exc:
                    log_email_delivery(
                        client_id=client_id,
                        email_type='customer_invoice_reminder',
                        recipient_email=row['recipient_email'],
                        recipient_name=row['client_name'],
                        subject=f'Reminder: invoice #{row["job_number"] or row["id"]}',
                        status='failed',
                        error_message=str(exc)[:500],
                        created_by_user_id=user['id'],
                    )
                    conn.commit()
                    flash(f'Invoice reminder failed: {exc}', 'error')
                return redirect(url_for('invoices', client_id=client_id))
            if action == 'mark_customer_invoice_paid':
                invoice_id = request.form.get('invoice_id', type=int)
                row = conn.execute(
                    '''SELECT *
                       FROM invoices
                       WHERE id=? AND client_id=? AND COALESCE(record_kind,'income_record')='customer_invoice' ''',
                    (invoice_id, client_id),
                ).fetchone()
                if not row:
                    flash('Customer invoice not found.', 'error')
                    return redirect(url_for('invoices', client_id=client_id))
                paid_at = now_iso()
                conn.execute(
                    '''UPDATE invoices
                       SET paid_amount=?, invoice_status='paid', customer_paid_at=?, payment_note=?, sent_at=CASE WHEN COALESCE(sent_at,'')='' THEN ? ELSE sent_at END
                       WHERE id=?''',
                    (
                        money(row['invoice_total_amount'] or 0),
                        paid_at,
                        request.form.get('payment_note', '').strip()[:300],
                        paid_at,
                        row['id'],
                    )
                )
                conn.commit()
                flash('Customer invoice marked paid.', 'success')
                return redirect(url_for('invoices', client_id=client_id))
            if action == 'send_customer_receipt':
                invoice_id = request.form.get('invoice_id', type=int)
                row = conn.execute(
                    '''SELECT i.*, c.business_name
                       FROM invoices i
                       JOIN clients c ON c.id = i.client_id
                       WHERE i.id=? AND i.client_id=? AND COALESCE(i.record_kind,'income_record')='customer_invoice' ''',
                    (invoice_id, client_id),
                ).fetchone()
                if not row:
                    flash('Customer invoice not found.', 'error')
                    return redirect(url_for('invoices', client_id=client_id))
                if not (row['recipient_email'] or '').strip():
                    flash('Add a recipient email before sending a receipt.', 'error')
                    return redirect(url_for('invoices', client_id=client_id))
                if invoice_payment_progress_status(row) != 'paid':
                    flash('Mark the invoice paid before sending a receipt.', 'error')
                    return redirect(url_for('invoices', client_id=client_id))
                token = ensure_invoice_public_token(conn, row['id'])
                try:
                    email_result = send_customer_receipt_email(
                        to_email=row['recipient_email'],
                        to_name=row['client_name'],
                        business_name=row['business_name'],
                        invoice_number=row['job_number'] or row['id'],
                        invoice_title=row['invoice_title'] or 'Customer Invoice',
                        invoice_link=public_invoice_url(token),
                        paid_amount=money(row['paid_amount'] or row['invoice_total_amount'] or 0),
                        paid_at=row['customer_paid_at'] or row['updated_at'] or now_iso(),
                    )
                    log_email_delivery(
                        client_id=client_id,
                        email_type=email_result['email_type'],
                        recipient_email=row['recipient_email'],
                        recipient_name=row['client_name'],
                        subject=email_result['subject'],
                        body_text=email_result['body_text'],
                        body_html=email_result['body_html'],
                        status='sent',
                        created_by_user_id=user['id'],
                    )
                    conn.commit()
                    flash('Payment receipt sent.', 'success')
                except Exception as exc:
                    log_email_delivery(
                        client_id=client_id,
                        email_type='customer_receipt',
                        recipient_email=row['recipient_email'],
                        recipient_name=row['client_name'],
                        subject=f'Receipt for invoice #{row["job_number"] or row["id"]}',
                        status='failed',
                        error_message=str(exc)[:500],
                        created_by_user_id=user['id'],
                    )
                    conn.commit()
                    flash(f'Receipt send failed: {exc}', 'error')
                return redirect(url_for('invoices', client_id=client_id))
            next_job = conn.execute('SELECT COALESCE(MAX(job_number),0)+1 n FROM invoices WHERE client_id=?', (client_id,)).fetchone()['n']
            gross_amount = request.form.get('paid_amount', type=float) or 0
            conn.execute(
                '''INSERT INTO invoices (
                    client_id, job_number, record_kind, invoice_title, client_name, recipient_email, client_address,
                    invoice_total_amount, paid_amount, invoice_date, due_date, invoice_status, public_invoice_token,
                    public_payment_link, notes, income_category, sales_tax_amount, sales_tax_paid
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (
                    client_id,
                    next_job,
                    'income_record',
                    'Income Record',
                    request.form.get('client_name', '').strip(),
                    '',
                    request.form.get('client_address', '').strip(),
                    gross_amount,
                    gross_amount,
                    request.form.get('invoice_date', '').strip(),
                    '',
                    'paid',
                    '',
                    '',
                    request.form.get('notes', '').strip(),
                    request.form.get('income_category', 'service_income').strip() or 'service_income',
                    request.form.get('sales_tax_amount', type=float) or 0,
                    1 if request.form.get('sales_tax_paid') else 0,
                )
            )
            conn.commit()
            flash('Income record saved.', 'success')
            return redirect(url_for('invoices', client_id=client_id))
        conn.execute(
            '''UPDATE invoices
               SET invoice_status='overdue'
               WHERE client_id=?
                 AND COALESCE(record_kind,'income_record')='customer_invoice'
                 AND COALESCE(invoice_status,'draft') IN ('sent','viewed','partial')
                 AND COALESCE(invoice_total_amount,0) > COALESCE(paid_amount,0)
                 AND COALESCE(due_date,'')<>''
                 AND due_date < ?''',
            (client_id, today_iso),
        )
        auto_reminder_count = automatic_invoice_reminders(conn, client_id=client_id, created_by_user_id=user['id'])
        if auto_reminder_count:
            conn.commit()
        rows = conn.execute('SELECT * FROM invoices WHERE client_id=? ORDER BY job_number DESC, id DESC', (client_id,)).fetchall()
        invoice_mileage_rows = conn.execute('''
            SELECT im.*, i.job_number, i.client_name
            FROM invoice_mileage_entries im
            LEFT JOIN invoices i ON i.id = im.invoice_id
            WHERE im.client_id=?
            ORDER BY im.trip_date DESC, im.id DESC
        ''', (client_id,)).fetchall()
        customer_rows = [row for row in rows if (row['record_kind'] or 'income_record') == 'customer_invoice']
        income_rows = [row for row in rows if (row['record_kind'] or 'income_record') == 'income_record']
        estimate_source_rows = conn.execute(
            "SELECT * FROM invoices WHERE client_id=? AND COALESCE(record_kind,'')='estimate' ORDER BY job_number DESC, id DESC LIMIT 6",
            (client_id,),
        ).fetchall()
        line_items_map = invoice_line_items_for_ids(conn, [row['id'] for row in customer_rows])
        customer_invoice_rows = []
        invoice_public_links = {}
        estimate_preview_rows = []
        estimate_preview_links = {}
        estimate_status_counts = {'draft': 0, 'sent': 0, 'viewed': 0, 'approved': 0, 'converted': 0}
        for row in customer_rows:
            token = ensure_invoice_public_token(conn, row['id'])
            current_status = invoice_payment_progress_status(row)
            row_dict = dict(row)
            row_dict['public_invoice_token'] = token
            row_dict['invoice_status'] = current_status
            row_dict['balance_due'] = invoice_balance_due(row)
            customer_invoice_rows.append(row_dict)
            invoice_public_links[row['id']] = public_invoice_url(token)
        for row in estimate_source_rows:
            token = ensure_invoice_public_token(conn, row['id'])
            current_status = estimate_current_status(row)
            row_dict = dict(row)
            row_dict['invoice_status'] = current_status
            estimate_preview_rows.append(row_dict)
            estimate_preview_links[row['id']] = public_estimate_url(token)
            if current_status in estimate_status_counts:
                estimate_status_counts[current_status] += 1
        conn.commit()
    if auto_reminder_count:
        flash(f'{auto_reminder_count} overdue invoice reminder(s) were sent automatically.', 'success')
    return render_template(
        'invoices.html',
        customer_invoices=customer_invoice_rows,
        sales_workspace_enabled=sales_workspace_enabled,
        customer_contacts=[dict(row) for row in customer_contact_rows],
        prefill_contact_id=(prefill_contact['id'] if prefill_contact else None),
        prefill_contact=dict(prefill_contact) if prefill_contact else None,
        income_records=income_rows,
        invoice_line_items_map=line_items_map,
        invoice_public_links=invoice_public_links,
        invoice_mileage_entries=invoice_mileage_rows,
        client=client,
        client_id=client_id,
        home_address=DEFAULT_HOME_ADDRESS,
        income_category_options=income_category_options(),
        income_category_labels=income_category_label_map(),
        invoice_status_labels=invoice_status_label_map(),
        estimate_preview_rows=estimate_preview_rows,
        estimate_preview_links=estimate_preview_links,
        estimate_status_counts=estimate_status_counts,
        estimate_status_labels=estimate_status_label_map(),
        today=today_iso,
        default_due_date=default_due_date,
        auto_reminder_count=auto_reminder_count,
    )


@app.route('/estimates', methods=['GET', 'POST'])
@login_required
def estimates():
    user = current_user()
    client_id = selected_client_id(user, 'post' if request.method == 'POST' else 'get')
    today_iso = date.today().isoformat()
    default_valid_until = (date.today() + timedelta(days=14)).isoformat()
    prefill_contact_id = request.values.get('customer_contact_id', type=int)
    with get_conn() as conn:
        client = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
        if not client or not allowed_client(user, client_id):
            abort(403)
        if not premium_sales_access_enabled(client):
            return premium_sales_redirect(client_id)
        customer_contact_rows = conn.execute(
            '''SELECT *
               FROM customer_contacts
               WHERE client_id=? AND COALESCE(status,'active')='active'
               ORDER BY LOWER(customer_name), id DESC''',
            (client_id,),
        ).fetchall()
        customer_contact_lookup = {row['id']: row for row in customer_contact_rows}
        prefill_contact = customer_contact_lookup.get(prefill_contact_id)
        if request.method == 'POST':
            action = request.form.get('action', 'create_estimate').strip()
            if action == 'create_estimate':
                errors: list[str] = []
                selected_contact = customer_contact_lookup.get(request.form.get('customer_contact_id', type=int))
                selected_contact_id = selected_contact['id'] if selected_contact else None
                customer_name = request.form.get('client_name', '').strip()
                recipient_email = request.form.get('recipient_email', '').strip().lower()
                invoice_date = request.form.get('invoice_date', '').strip() or today_iso
                valid_until = request.form.get('estimate_expiration_date', '').strip()
                estimate_title = request.form.get('invoice_title', '').strip() or 'Project Estimate'
                client_address = request.form.get('client_address', '').strip()
                notes = request.form.get('notes', '').strip()
                customer_phone = request.form.get('customer_phone', '').strip()
                if selected_contact:
                    customer_name = customer_name or (selected_contact['customer_name'] or '').strip()
                    recipient_email = recipient_email or (selected_contact['customer_email'] or '').strip().lower()
                    client_address = client_address or (selected_contact['customer_address'] or '').strip()
                    customer_phone = customer_phone or (selected_contact['customer_phone'] or '').strip()
                items, item_errors = parse_invoice_line_items(request.form)
                errors.extend(item_errors)
                if not customer_name:
                    errors.append('Customer name is required.')
                if not recipient_email or '@' not in recipient_email:
                    errors.append('A valid recipient email is required.')
                if not parse_date(invoice_date):
                    errors.append('Estimate date is invalid.')
                if valid_until and not parse_date(valid_until):
                    errors.append('Valid-until date is invalid.')
                sales_tax_amount = normalize_money_amount(request.form.get('sales_tax_amount', '0') or '0')
                if sales_tax_amount is None or sales_tax_amount < 0:
                    errors.append('Sales tax amount is invalid.')
                subtotal = invoice_subtotal(items) if not item_errors else Decimal('0.00')
                total_amount = (subtotal + (sales_tax_amount or Decimal('0.00'))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                if total_amount <= 0:
                    errors.append('Estimate total must be above zero.')
                if errors:
                    for error in errors:
                        flash(error, 'error')
                    return redirect(url_for('estimates', client_id=client_id))
                next_job = conn.execute('SELECT COALESCE(MAX(job_number),0)+1 n FROM invoices WHERE client_id=?', (client_id,)).fetchone()['n']
                token = generate_invoice_public_token()
                while conn.execute('SELECT 1 FROM invoices WHERE public_invoice_token=? LIMIT 1', (token,)).fetchone():
                    token = generate_invoice_public_token()
                saved_contact_id = upsert_customer_contact(
                    conn,
                    client_id=client_id,
                    customer_name=customer_name,
                    customer_email=recipient_email,
                    customer_phone=customer_phone,
                    customer_address=client_address,
                    customer_notes=notes,
                    created_by_user_id=user['id'],
                )
                customer_contact_id = selected_contact_id or saved_contact_id
                cursor = conn.execute(
                    '''INSERT INTO invoices (
                        client_id, customer_contact_id, job_number, record_kind, invoice_title, client_name, recipient_email, client_address,
                        invoice_total_amount, paid_amount, invoice_date, due_date, estimate_expiration_date, invoice_status,
                        public_invoice_token, public_payment_link, sent_at, last_reminder_at, reminder_count,
                        customer_viewed_at, customer_paid_at, approved_at, declined_at, converted_invoice_id,
                        payment_note, notes, income_category, sales_tax_amount, sales_tax_paid
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (
                        client_id,
                        customer_contact_id,
                        next_job,
                        'estimate',
                        estimate_title,
                        customer_name,
                        recipient_email,
                        client_address,
                        float(total_amount),
                        0,
                        invoice_date,
                        '',
                        valid_until,
                        'draft',
                        token,
                        '',
                        '',
                        '',
                        0,
                        '',
                        '',
                        '',
                        '',
                        None,
                        '',
                        notes,
                        'service_income',
                        float(sales_tax_amount or Decimal('0.00')),
                        0,
                    )
                )
                estimate_id = cursor.lastrowid
                for item in items:
                    conn.execute(
                        '''INSERT INTO invoice_line_items (invoice_id, sort_order, description, quantity, unit_price, line_total)
                           VALUES (?,?,?,?,?,?)''',
                        (
                            estimate_id,
                            item['sort_order'],
                            item['description'],
                            item['quantity'],
                            item['unit_price'],
                            item['line_total'],
                        )
                    )
                if request.form.get('send_now'):
                    try:
                        email_result = send_customer_estimate_email(
                            to_email=recipient_email,
                            to_name=customer_name,
                            business_name=client['business_name'],
                            estimate_number=next_job,
                            estimate_title=estimate_title,
                            estimate_link=public_estimate_url(token),
                            valid_until=valid_until,
                            total_amount=float(total_amount),
                        )
                        conn.execute(
                            'UPDATE invoices SET invoice_status=?, sent_at=? WHERE id=?',
                            ('expired' if valid_until and valid_until < today_iso else 'sent', now_iso(), estimate_id),
                        )
                        log_email_delivery(
                            client_id=client_id,
                            email_type=email_result['email_type'],
                            recipient_email=recipient_email,
                            recipient_name=customer_name,
                            subject=email_result['subject'],
                            body_text=email_result['body_text'],
                            body_html=email_result['body_html'],
                            status='sent',
                            created_by_user_id=user['id'],
                        )
                        flash('Estimate saved and sent.', 'success')
                    except Exception as exc:
                        log_email_delivery(
                            client_id=client_id,
                            email_type='customer_estimate',
                            recipient_email=recipient_email,
                            recipient_name=customer_name,
                            subject=f'Estimate #{next_job} from {client["business_name"]}',
                            status='failed',
                            error_message=str(exc)[:500],
                            created_by_user_id=user['id'],
                        )
                        flash(f'Estimate saved, but sending failed: {exc}', 'error')
                else:
                    flash('Estimate saved.', 'success')
                conn.commit()
                return redirect(url_for('estimates', client_id=client_id))
            if action == 'send_estimate':
                estimate_id = request.form.get('estimate_id', type=int)
                row = conn.execute(
                    "SELECT i.*, c.business_name FROM invoices i JOIN clients c ON c.id=i.client_id WHERE i.id=? AND i.client_id=? AND COALESCE(i.record_kind,'')='estimate'",
                    (estimate_id, client_id),
                ).fetchone()
                if not row:
                    flash('Estimate not found.', 'error')
                    return redirect(url_for('estimates', client_id=client_id))
                token = ensure_invoice_public_token(conn, row['id'])
                try:
                    email_result = send_customer_estimate_email(
                        to_email=row['recipient_email'],
                        to_name=row['client_name'],
                        business_name=row['business_name'],
                        estimate_number=row['job_number'] or row['id'],
                        estimate_title=row['invoice_title'] or 'Project Estimate',
                        estimate_link=public_estimate_url(token),
                        valid_until=row['estimate_expiration_date'] or '',
                        total_amount=money(row['invoice_total_amount'] or 0),
                    )
                    conn.execute(
                        'UPDATE invoices SET invoice_status=?, sent_at=? WHERE id=?',
                        ('expired' if (row['estimate_expiration_date'] or '') and (row['estimate_expiration_date'] or '') < today_iso else 'sent', now_iso(), row['id']),
                    )
                    log_email_delivery(
                        client_id=client_id,
                        email_type=email_result['email_type'],
                        recipient_email=row['recipient_email'],
                        recipient_name=row['client_name'],
                        subject=email_result['subject'],
                        body_text=email_result['body_text'],
                        body_html=email_result['body_html'],
                        status='sent',
                        created_by_user_id=user['id'],
                    )
                    conn.commit()
                    flash('Estimate sent.', 'success')
                except Exception as exc:
                    log_email_delivery(
                        client_id=client_id,
                        email_type='customer_estimate',
                        recipient_email=row['recipient_email'],
                        recipient_name=row['client_name'],
                        subject=f'Estimate #{row["job_number"] or row["id"]} from {row["business_name"]}',
                        status='failed',
                        error_message=str(exc)[:500],
                        created_by_user_id=user['id'],
                    )
                    conn.commit()
                    flash(f'Estimate send failed: {exc}', 'error')
                return redirect(url_for('estimates', client_id=client_id))
            if action == 'convert_estimate_to_invoice':
                estimate_id = request.form.get('estimate_id', type=int)
                row = conn.execute(
                    "SELECT * FROM invoices WHERE id=? AND client_id=? AND COALESCE(record_kind,'')='estimate'",
                    (estimate_id, client_id),
                ).fetchone()
                if not row:
                    flash('Estimate not found.', 'error')
                    return redirect(url_for('estimates', client_id=client_id))
                items = conn.execute(
                    'SELECT * FROM invoice_line_items WHERE invoice_id=? ORDER BY sort_order, id',
                    (estimate_id,),
                ).fetchall()
                invoice_id = convert_estimate_to_invoice_document(conn, row, items, actor_user_id=user['id'])
                conn.commit()
                flash('Estimate converted into a customer invoice.', 'success')
                return redirect(url_for('invoice_print', invoice_id=invoice_id))

        conn.execute(
            """UPDATE invoices
               SET invoice_status='expired'
               WHERE client_id=?
                 AND COALESCE(record_kind,'')='estimate'
                 AND COALESCE(invoice_status,'draft') IN ('draft','sent','viewed')
                 AND COALESCE(estimate_expiration_date,'')<>''
                 AND estimate_expiration_date < ?""",
            (client_id, today_iso),
        )
        rows = conn.execute(
            "SELECT * FROM invoices WHERE client_id=? AND COALESCE(record_kind,'')='estimate' ORDER BY job_number DESC, id DESC",
            (client_id,),
        ).fetchall()
        line_items_map = invoice_line_items_for_ids(conn, [row['id'] for row in rows])
        estimate_rows = []
        estimate_public_links = {}
        for row in rows:
            token = ensure_invoice_public_token(conn, row['id'])
            row_dict = dict(row)
            row_dict['invoice_status'] = estimate_current_status(row)
            estimate_rows.append(row_dict)
            estimate_public_links[row['id']] = public_estimate_url(token)
        conn.commit()
    return render_template(
        'estimates.html',
        client=client,
        client_id=client_id,
        customer_contacts=[dict(row) for row in customer_contact_rows],
        prefill_contact_id=(prefill_contact['id'] if prefill_contact else None),
        prefill_contact=dict(prefill_contact) if prefill_contact else None,
        estimates=estimate_rows,
        estimate_line_items_map=line_items_map,
        estimate_public_links=estimate_public_links,
        estimate_status_labels=estimate_status_label_map(),
        today=today_iso,
        default_valid_until=default_valid_until,
    )


@app.route('/invoice/<int:invoice_id>')
@login_required
def invoice_print(invoice_id):
    user = current_user()
    with get_conn() as conn:
        row = conn.execute(
            '''SELECT i.*, c.business_name, c.contact_name business_contact_name, c.email business_email, c.phone business_phone, c.address business_address
               FROM invoices i
               JOIN clients c ON c.id=i.client_id
               WHERE i.id=?''',
            (invoice_id,),
        ).fetchone()
        line_items = conn.execute(
            'SELECT * FROM invoice_line_items WHERE invoice_id=? ORDER BY sort_order, id',
            (invoice_id,),
        ).fetchall()
    if not row or not allowed_client(user, row['client_id']):
        abort(403)
    record_kind = row['record_kind'] or 'income_record'
    status = estimate_current_status(row) if record_kind == 'estimate' else invoice_payment_progress_status(row)
    token = (row['public_invoice_token'] or '').strip()
    return render_template(
        'invoice_print.html',
        invoice=row,
        line_items=line_items,
        invoice_status_label=(estimate_status_label_map().get(status, 'Draft') if record_kind == 'estimate' else invoice_status_label_map().get(status, 'Draft')),
        balance_due=invoice_balance_due(row),
        public_invoice_link=(public_estimate_url(token) if token and record_kind == 'estimate' else (public_invoice_url(token) if token else '')),
        pay_online_link=(row['public_payment_link'] or '').strip(),
    )


@app.route('/customer-invoice/<token>')
def customer_invoice_public(token):
    with get_conn() as conn:
        row = conn.execute(
            '''SELECT i.*, c.business_name, c.contact_name business_contact_name, c.email business_email, c.phone business_phone, c.address business_address
               FROM invoices i
               JOIN clients c ON c.id = i.client_id
               WHERE i.public_invoice_token=? AND COALESCE(i.record_kind,'income_record')='customer_invoice' ''',
            ((token or '').strip(),),
        ).fetchone()
        if not row:
            abort(404)
        line_items = conn.execute(
            'SELECT * FROM invoice_line_items WHERE invoice_id=? ORDER BY sort_order, id',
            (row['id'],),
        ).fetchall()
        status = invoice_payment_progress_status(row)
        viewed_at = row['customer_viewed_at'] or now_iso()
        updated_status = status
        if status in {'draft', 'sent'} and invoice_balance_due(row) > 0:
            updated_status = 'overdue' if (row['due_date'] or '').strip() and (row['due_date'] or '') < date.today().isoformat() else 'viewed'
        conn.execute(
            'UPDATE invoices SET customer_viewed_at=?, invoice_status=? WHERE id=?',
            (viewed_at, updated_status, row['id']),
        )
        conn.commit()
    return render_template(
        'invoice_public.html',
        invoice=row,
        line_items=line_items,
        invoice_status_label=invoice_status_label_map().get(updated_status, 'Draft'),
        balance_due=invoice_balance_due(row),
        pay_online_link=(row['public_payment_link'] or '').strip(),
    )


@app.route('/customer-invoice/<token>/pay')
def customer_invoice_pay(token):
    with get_conn() as conn:
        row = conn.execute(
            '''SELECT *
               FROM invoices
               WHERE public_invoice_token=? AND COALESCE(record_kind,'income_record')='customer_invoice' ''',
            ((token or '').strip(),),
        ).fetchone()
        if not row:
            abort(404)
        payment_link = (row['public_payment_link'] or '').strip()
        if not payment_link:
            return redirect(public_invoice_url((token or '').strip()))
        status = invoice_payment_progress_status(row)
        conn.execute(
            'UPDATE invoices SET customer_viewed_at=?, invoice_status=? WHERE id=?',
            (row['customer_viewed_at'] or now_iso(), 'overdue' if status == 'overdue' else 'viewed', row['id']),
        )
        conn.commit()
    return redirect(payment_link)


@app.route('/customer-estimate/<token>', methods=['GET', 'POST'])
def customer_estimate_public(token):
    with get_conn() as conn:
        row = conn.execute(
            '''SELECT i.*, c.business_name, c.contact_name business_contact_name, c.email business_email, c.phone business_phone, c.address business_address
               FROM invoices i
               JOIN clients c ON c.id = i.client_id
               WHERE i.public_invoice_token=? AND COALESCE(i.record_kind,'')='estimate' ''',
            ((token or '').strip(),),
        ).fetchone()
        if not row:
            abort(404)
        line_items = conn.execute(
            'SELECT * FROM invoice_line_items WHERE invoice_id=? ORDER BY sort_order, id',
            (row['id'],),
        ).fetchall()
        status = estimate_current_status(row)
        viewed_at = row['customer_viewed_at'] or now_iso()
        if request.method == 'POST':
            action = request.form.get('action', '').strip()
            if action == 'approve' and status not in {'converted', 'approved', 'declined'}:
                status = 'approved'
                conn.execute(
                    "UPDATE invoices SET invoice_status='approved', approved_at=?, customer_viewed_at=? WHERE id=?",
                    (now_iso(), viewed_at, row['id']),
                )
                conn.commit()
            elif action == 'decline' and status not in {'converted', 'approved', 'declined'}:
                status = 'declined'
                conn.execute(
                    "UPDATE invoices SET invoice_status='declined', declined_at=?, customer_viewed_at=? WHERE id=?",
                    (now_iso(), viewed_at, row['id']),
                )
                conn.commit()
            return redirect(url_for('customer_estimate_public', token=(token or '').strip()))
        updated_status = status
        if status in {'draft', 'sent'}:
            updated_status = 'expired' if (row['estimate_expiration_date'] or '').strip() and (row['estimate_expiration_date'] or '') < date.today().isoformat() else 'viewed'
        conn.execute(
            'UPDATE invoices SET customer_viewed_at=?, invoice_status=? WHERE id=?',
            (viewed_at, updated_status, row['id']),
        )
        conn.commit()
    return render_template(
        'estimate_public.html',
        estimate=row,
        line_items=line_items,
        estimate_status_label=estimate_status_label_map().get(updated_status, 'Draft'),
        estimate_status_code=updated_status,
    )


@app.route('/workers', methods=['GET', 'POST'])
@login_required
def workers():
    user = current_user()
    client_id = selected_client_id(user, 'post' if request.method == 'POST' else 'get')
    with get_conn() as conn:
        if request.method == 'POST':
            action = request.form.get('action', 'add')
            if action == 'add':
                payout_cleaned, payout_errors = validate_worker_payout_setup(request.form)
                if payout_errors:
                    for error in payout_errors:
                        flash(error, 'error')
                    return redirect(url_for('workers', client_id=client_id))
                saved_at = now_iso()
                preferred_language = normalize_language(request.form.get('preferred_language'))
                conn.execute(
                    '''INSERT INTO workers (
                        client_id, name, worker_type, ssn, address, phone, email, hire_date, pay_notes, payroll_frequency,
                        role_classification, status, termination_date, termination_cause, payout_preference, deposit_bank_name,
                        deposit_account_holder_name, deposit_account_type, deposit_account_last4, deposit_routing_number_enc,
                        deposit_account_number_enc, zelle_contact, preferred_language, created_by_user_id, updated_at, updated_by_user_id
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (
                        client_id,
                        request.form.get('name', '').strip(),
                        request.form.get('worker_type', '1099').strip(),
                        request.form.get('ssn', '').strip(),
                        request.form.get('address', '').strip(),
                        request.form.get('phone', '').strip(),
                        request.form.get('email', '').strip(),
                        request.form.get('hire_date', '').strip(),
                        request.form.get('pay_notes', '').strip(),
                        request.form.get('payroll_frequency', 'weekly').strip(),
                        request.form.get('role_classification', '').strip(),
                        'active',
                        '',
                        '',
                        payout_cleaned['payout_preference'],
                        payout_cleaned['deposit_bank_name'],
                        payout_cleaned['deposit_account_holder_name'],
                        payout_cleaned['deposit_account_type'],
                        payout_cleaned['deposit_account_last4'],
                        payout_cleaned['deposit_routing_number_enc'],
                        payout_cleaned['deposit_account_number_enc'],
                        payout_cleaned['zelle_contact'],
                        preferred_language,
                        user['id'],
                        saved_at,
                        user['id'],
                    )
                )
                worker_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
                conn.execute('INSERT OR IGNORE INTO w4_answers (worker_id, signed_date) VALUES (?,?)', (worker_id, date.today().isoformat()))
                log_worker_profile_history(conn, worker_id=worker_id, client_id=client_id, action='created', changed_by_user_id=user['id'])
                conn.commit()
                flash('Worker saved.', 'success')
                return redirect(url_for('workers', client_id=client_id, worker_id=worker_id))
            worker_id = request.form.get('worker_id', type=int)
            worker = conn.execute('SELECT * FROM workers WHERE id=? AND client_id=?', (worker_id, client_id)).fetchone() if worker_id else None
            if not worker:
                abort(403)
            if action == 'edit':
                payout_cleaned, payout_errors = validate_worker_payout_setup(request.form, existing=worker)
                if payout_errors:
                    for error in payout_errors:
                        flash(error, 'error')
                    return redirect(url_for('workers', client_id=client_id, worker_id=worker_id))
                try:
                    saved_at = now_iso()
                    preferred_language = normalize_language(request.form.get('preferred_language') or worker['preferred_language'])
                    conn.execute(
                        '''UPDATE workers
                           SET name=?, worker_type=?, ssn=?, address=?, phone=?, email=?, hire_date=?, pay_notes=?,
                               payroll_frequency=?, role_classification=?, payout_preference=?, deposit_bank_name=?,
                               deposit_account_holder_name=?, deposit_account_type=?, deposit_account_last4=?,
                               deposit_routing_number_enc=?, deposit_account_number_enc=?, zelle_contact=?, preferred_language=?,
                               updated_at=?, updated_by_user_id=?
                           WHERE id=?''',
                        (
                            request.form.get('name', '').strip(),
                            request.form.get('worker_type', '1099').strip(),
                            request.form.get('ssn', '').strip(),
                            request.form.get('address', '').strip(),
                            request.form.get('phone', '').strip(),
                            request.form.get('email', '').strip(),
                            request.form.get('hire_date', '').strip(),
                            request.form.get('pay_notes', '').strip(),
                            request.form.get('payroll_frequency', 'weekly').strip(),
                            request.form.get('role_classification', '').strip(),
                            payout_cleaned['payout_preference'],
                            payout_cleaned['deposit_bank_name'],
                            payout_cleaned['deposit_account_holder_name'],
                            payout_cleaned['deposit_account_type'],
                            payout_cleaned['deposit_account_last4'],
                            payout_cleaned['deposit_routing_number_enc'],
                            payout_cleaned['deposit_account_number_enc'],
                            payout_cleaned['zelle_contact'],
                            preferred_language,
                            saved_at,
                            user['id'],
                            worker_id,
                        )
                    )
                    log_worker_profile_history(conn, worker_id=worker_id, client_id=client_id, action='updated', changed_by_user_id=user['id'])
                    conn.commit()
                    flash('Worker updated.', 'success')
                except sqlite3.Error:
                    conn.rollback()
                    flash('Worker changes could not be saved.', 'error')
                return redirect(url_for('workers', client_id=client_id, worker_id=worker_id))
            if action == 'terminate':
                terminated_at = now_iso()
                conn.execute('UPDATE workers SET status=?, termination_date=?, termination_cause=?, updated_at=?, updated_by_user_id=? WHERE id=?', ('terminated', request.form.get('termination_date', '').strip(), request.form.get('termination_cause', '').strip(), terminated_at, user['id'], worker_id))
                log_worker_profile_history(conn, worker_id=worker_id, client_id=client_id, action='terminated', changed_by_user_id=user['id'])
                conn.commit()
                flash('Worker terminated.', 'success')
                return redirect(url_for('workers', client_id=client_id, worker_id=worker_id))
            if action == 'reactivate':
                reactivated_at = now_iso()
                conn.execute('UPDATE workers SET status=?, termination_date=?, termination_cause=?, updated_at=?, updated_by_user_id=? WHERE id=?', ('active', '', '', reactivated_at, user['id'], worker_id))
                log_worker_profile_history(conn, worker_id=worker_id, client_id=client_id, action='reactivated', changed_by_user_id=user['id'])
                conn.commit()
                flash('Worker reactivated.', 'success')
                return redirect(url_for('workers', client_id=client_id, worker_id=worker_id))
            if action == 'update_portal':
                portal_email = request.form.get('portal_email', '').strip().lower()
                portal_password = request.form.get('portal_password', '').strip()
                portal_enabled = 1 if request.form.get('portal_access_enabled') else 0
                if portal_enabled and not portal_email:
                    flash('Worker portal email is required when portal access is enabled.', 'error')
                    return redirect(url_for('workers', client_id=client_id, worker_id=worker_id))
                if portal_password and len(portal_password) < 4:
                    flash('Worker portal password must be at least 4 characters.', 'error')
                    return redirect(url_for('workers', client_id=client_id, worker_id=worker_id))
                password_hash = worker['portal_password_hash'] or ''
                if portal_password:
                    password_hash = generate_password_hash(portal_password)
                approval_status = 'approved'
                requested_at = worker['portal_requested_at'] or ''
                approved_at = worker['portal_approved_at'] or ''
                approved_by = worker['portal_approved_by']
                if portal_enabled:
                    approval_status = 'approved'
                    approved_at = datetime.now().isoformat(timespec='seconds')
                    approved_by = user['id']
                    if not requested_at:
                        requested_at = approved_at
                else:
                    approval_status = 'disabled'
                    approved_at = ''
                    approved_by = None
                target_portal_email = portal_email or worker['email']
                portal_saved_at = now_iso()
                conn.execute('UPDATE workers SET email=?, portal_access_enabled=?, portal_password_hash=?, portal_approval_status=?, portal_requested_at=?, portal_approved_at=?, portal_approved_by=?, updated_at=?, updated_by_user_id=? WHERE id=?', (target_portal_email, portal_enabled, password_hash, approval_status, requested_at, approved_at, approved_by, portal_saved_at, user['id'], worker_id))
                client_row = conn.execute('SELECT business_name FROM clients WHERE id=?', (client_id,)).fetchone()
                if portal_enabled:
                    log_account_activity(conn, client_id=client_id, account_type='worker_portal', account_email=target_portal_email, account_name=worker['name'], created_by_user_id=user['id'], status='auto_approved', detail='Business created worker portal access and it was activated automatically.')
                log_worker_profile_history(
                    conn,
                    worker_id=worker_id,
                    client_id=client_id,
                    action='portal_access_updated',
                    changed_by_user_id=user['id'],
                    detail=f"Portal access {'enabled' if portal_enabled else 'disabled'}.",
                )
                conn.commit()
                welcome_sent = False
                welcome_error = ''
                if portal_enabled and approval_status == 'approved' and target_portal_email and smtp_email_ready():
                    try:
                        send_welcome_email(
                            target_portal_email,
                            worker['name'],
                            'worker',
                            login_path='/worker-login',
                            business_name=(client_row['business_name'] if client_row else '')
                        )
                        welcome_sent = True
                    except Exception as e:
                        welcome_error = str(e)[:200]
                if portal_enabled and welcome_sent:
                    flash('Worker portal access updated and approved. Welcome email sent.', 'success')
                elif portal_enabled and smtp_email_ready():
                    flash(f'Worker portal access updated and approved, but welcome email failed: {welcome_error}', 'error')
                elif portal_enabled:
                    flash('Worker portal access updated and approved.', 'success')
                else:
                    flash('Worker portal access updated.', 'success')
                return redirect(url_for('workers', client_id=client_id, worker_id=worker_id))
            if action == 'delete':
                has_payments = conn.execute('SELECT 1 FROM worker_payments WHERE worker_id=? LIMIT 1', (worker_id,)).fetchone()
                if has_payments:
                    flash('Worker has payment history and cannot be deleted. Terminate instead.', 'error')
                else:
                    log_worker_profile_history(conn, worker_id=worker_id, client_id=client_id, action='deleted', changed_by_user_id=user['id'], snapshot=worker)
                    conn.execute('DELETE FROM worker_time_off_requests WHERE worker_id=?', (worker_id,))
                    conn.execute('DELETE FROM worker_messages WHERE worker_id=?', (worker_id,))
                    conn.execute('DELETE FROM worker_time_entries WHERE worker_id=?', (worker_id,))
                    conn.execute('DELETE FROM w4_answers WHERE worker_id=?', (worker_id,))
                    conn.execute('DELETE FROM workers WHERE id=?', (worker_id,))
                    conn.commit()
                    flash('Worker deleted.', 'success')
                    return redirect(url_for('workers', client_id=client_id))
            if action == 'add_notice':
                title = request.form.get('notice_title', '').strip()
                body = request.form.get('notice_body', '').strip()
                if not title or not body:
                    flash('Policy title and notice text are required.', 'error')
                else:
                    conn.execute(
                        '''INSERT INTO worker_policy_notices (client_id, title, body, created_by_user_id, is_active)
                           VALUES (?,?,?,?,1)''',
                        (client_id, title[:120], body[:3000], user['id'])
                    )
                    conn.commit()
                    flash('Business policy / notice added.', 'success')
                return redirect(url_for('workers', client_id=client_id, worker_id=worker_id or request.args.get('worker_id', type=int) or ''))
            if action == 'edit_notice':
                notice_id = request.form.get('notice_id', type=int)
                title = request.form.get('notice_title', '').strip()
                body = request.form.get('notice_body', '').strip()
                is_active = 1 if request.form.get('is_active') else 0
                notice = conn.execute('SELECT * FROM worker_policy_notices WHERE id=? AND client_id=?', (notice_id, client_id)).fetchone() if notice_id else None
                if not notice:
                    flash('Policy / notice not found.', 'error')
                elif not title or not body:
                    flash('Policy title and notice text are required.', 'error')
                else:
                    conn.execute(
                        '''UPDATE worker_policy_notices
                           SET title=?, body=?, is_active=?, updated_at=CURRENT_TIMESTAMP
                           WHERE id=? AND client_id=?''',
                        (title[:120], body[:3000], is_active, notice_id, client_id)
                    )
                    conn.commit()
                    flash('Business policy / notice updated.', 'success')
                return redirect(url_for('workers', client_id=client_id, worker_id=worker_id or request.args.get('worker_id', type=int) or ''))
            if action == 'delete_notice':
                notice_id = request.form.get('notice_id', type=int)
                conn.execute('DELETE FROM worker_policy_notices WHERE id=? AND client_id=?', (notice_id, client_id))
                conn.commit()
                flash('Business policy / notice removed.', 'success')
                return redirect(url_for('workers', client_id=client_id, worker_id=worker_id or request.args.get('worker_id', type=int) or ''))
        rows = conn.execute('SELECT * FROM workers WHERE client_id=? ORDER BY CASE WHEN status="active" THEN 0 WHEN status="terminated" THEN 1 ELSE 2 END, name', (client_id,)).fetchall()
        client = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
        selected_worker_id = request.args.get('worker_id', type=int) or (rows[0]['id'] if rows else None)
        selected_worker = conn.execute(
            '''SELECT w.*, creator.full_name created_by_name, updater.full_name updated_by_name
               FROM workers w
               LEFT JOIN users creator ON creator.id = w.created_by_user_id
               LEFT JOIN users updater ON updater.id = w.updated_by_user_id
               WHERE w.id=?''',
            (selected_worker_id,)
        ).fetchone() if selected_worker_id else None
        answers = conn.execute('SELECT * FROM w4_answers WHERE worker_id=?', (selected_worker_id,)).fetchone() if selected_worker_id else None
        policy_notices = conn.execute('SELECT * FROM worker_policy_notices WHERE client_id=? ORDER BY updated_at DESC, id DESC', (client_id,)).fetchall()
    return render_template('workers.html', workers=rows, client=client, client_id=client_id, selected_worker=selected_worker, answers=answers, worker_login_url=url_for('worker_login'), policy_notices=policy_notices, worker_payout_preferences=worker_payout_preference_options())


@app.route('/workers/<int:worker_id>/w4', methods=['POST'])
@login_required
def save_worker_w4(worker_id):
    user = current_user()
    with get_conn() as conn:
        worker = conn.execute('SELECT * FROM workers WHERE id=?', (worker_id,)).fetchone()
        if not worker or not allowed_client(user, worker['client_id']):
            abort(403)
        existing = conn.execute('SELECT id FROM w4_answers WHERE worker_id=?', (worker_id,)).fetchone()
        data = (
            request.form.get('filing_status', ''),
            1 if request.form.get('multiple_jobs') else 0,
            request.form.get('qualifying_children', type=float) or 0,
            request.form.get('other_dependents', type=float) or 0,
            request.form.get('other_income', type=float) or 0,
            request.form.get('deductions', type=float) or 0,
            request.form.get('extra_withholding', type=float) or 0,
            request.form.get('signature_name', '').strip(),
            request.form.get('signed_date', '').strip(),
            datetime.now().isoformat(timespec='seconds'),
        )
        if existing:
            conn.execute('UPDATE w4_answers SET filing_status=?, multiple_jobs=?, qualifying_children=?, other_dependents=?, other_income=?, deductions=?, extra_withholding=?, signature_name=?, signed_date=?, updated_at=? WHERE worker_id=?', data + (worker_id,))
        else:
            conn.execute('INSERT INTO w4_answers (filing_status, multiple_jobs, qualifying_children, other_dependents, other_income, deductions, extra_withholding, signature_name, signed_date, updated_at, worker_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)', data + (worker_id,))
        conn.commit()
    flash('W-4 answers saved.', 'success')
    return redirect(url_for('workers', client_id=worker['client_id'], worker_id=worker_id))


@app.route('/worker-payments', methods=['GET', 'POST'])
@login_required
def worker_payments():
    user = current_user()
    client_id = selected_client_id(user, 'post' if request.method == 'POST' else 'get')
    with get_conn() as conn:
        workers = conn.execute('SELECT * FROM workers WHERE client_id=? ORDER BY CASE WHEN status="active" THEN 0 ELSE 1 END, name', (client_id,)).fetchall()
        if request.method == 'POST':
            action = request.form.get('action', 'add').strip().lower()
            if action == 'add':
                worker_id = request.form.get('worker_id', type=int)
                amount = request.form.get('amount', type=float) or 0
                payment_date = request.form.get('payment_date', '').strip()
                payment_method = normalize_worker_payment_method(request.form.get('payment_method', 'direct_deposit'))
                payment_status = normalize_worker_payment_status(request.form.get('payment_status', 'paid'))
                reference_number = request.form.get('reference_number', '').strip()[:120]
                note = request.form.get('note', '').strip()
                worker = conn.execute('SELECT * FROM workers WHERE id=? AND client_id=?', (worker_id, client_id)).fetchone() if worker_id else None
                if not worker:
                    flash('Select a valid worker.', 'error')
                elif amount <= 0:
                    flash('Enter an amount greater than zero.', 'error')
                elif not payment_date:
                    flash('Enter a payment date.', 'error')
                else:
                    conn.execute(
                        'INSERT INTO worker_payments (worker_id, payment_date, amount, payment_method, payment_status, reference_number, note) VALUES (?,?,?,?,?,?,?)',
                        (worker_id, payment_date, amount, payment_method, payment_status, reference_number, note)
                    )
                    conn.commit()
                    flash('Worker payment saved.', 'success')
            elif action == 'update':
                payment_id = request.form.get('payment_id', type=int)
                row = conn.execute('SELECT wp.*, w.client_id FROM worker_payments wp JOIN workers w ON w.id=wp.worker_id WHERE wp.id=?', (payment_id,)).fetchone() if payment_id else None
                amount = request.form.get('amount', type=float) or 0
                if not row or int(row['client_id'] or 0) != int(client_id):
                    flash('Worker payment not found.', 'error')
                elif amount <= 0:
                    flash('Enter an amount greater than zero.', 'error')
                else:
                    conn.execute(
                        '''UPDATE worker_payments
                           SET payment_date=?, amount=?, payment_method=?, payment_status=?, reference_number=?, note=?
                           WHERE id=?''',
                        (
                            request.form.get('payment_date', '').strip(),
                            amount,
                            normalize_worker_payment_method(request.form.get('payment_method', 'direct_deposit')),
                            normalize_worker_payment_status(request.form.get('payment_status', 'paid')),
                            request.form.get('reference_number', '').strip()[:120],
                            request.form.get('note', '').strip(),
                            payment_id,
                        )
                    )
                    conn.commit()
                    flash('Worker payment updated.', 'success')
            return redirect(url_for('worker_payments', client_id=client_id))
        rows = conn.execute('SELECT wp.*, w.name worker_name, w.worker_type FROM worker_payments wp JOIN workers w ON w.id=wp.worker_id WHERE w.client_id=? ORDER BY payment_date DESC, wp.id DESC', (client_id,)).fetchall()
        client = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
    return render_template('worker_payments.html', payments=rows, workers=workers, client=client, client_id=client_id, today=date.today().isoformat(), worker_payment_methods=worker_payment_method_options(), worker_payment_statuses=worker_payment_status_options(), worker_payment_method_labels=worker_payment_method_label_map(), worker_payment_status_labels=worker_payment_status_label_map())


@app.route('/gas', methods=['GET', 'POST'])
@login_required
def gas():
    user = current_user()
    client_id = selected_client_id(user, 'post' if request.method == 'POST' else 'get')
    with get_conn() as conn:
        if request.method == 'POST':
            conn.execute('INSERT INTO gas_entries (client_id, week_start, amount, note) VALUES (?,?,?,?)', (client_id, request.form.get('week_start', '').strip(), request.form.get('amount', type=float) or 0, request.form.get('note', '').strip()))
            conn.commit()
            flash('Gas entry saved.', 'success')
            return redirect(url_for('gas', client_id=client_id))
        rows = conn.execute('SELECT * FROM gas_entries WHERE client_id=? ORDER BY week_start DESC, id DESC', (client_id,)).fetchall()
        client = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
    return render_template('gas.html', gas_entries=rows, client=client, client_id=client_id)


@app.route('/materials', methods=['GET', 'POST'])
@login_required
def materials():
    user = current_user()
    client_id = selected_client_id(user, 'post' if request.method == 'POST' else 'get')
    with get_conn() as conn:
        if request.method == 'POST':
            conn.execute('INSERT INTO materials (client_id, material_date, description, amount) VALUES (?,?,?,?)', (client_id, request.form.get('material_date', '').strip(), request.form.get('description', '').strip(), request.form.get('amount', type=float) or 0))
            conn.commit()
            flash('Material saved.', 'success')
            return redirect(url_for('materials', client_id=client_id))
        rows = conn.execute('SELECT * FROM materials WHERE client_id=? ORDER BY material_date DESC, id DESC', (client_id,)).fetchall()
        client = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
    return render_template('materials.html', materials=rows, client=client, client_id=client_id)


@app.route('/mileage', methods=['GET', 'POST'])
@login_required
def mileage():
    user = current_user()
    client_id = selected_client_id(user, 'post' if request.method == 'POST' else 'get')
    with get_conn() as conn:
        if request.method == 'POST':
            miles = request.form.get('miles', type=float) or 0
            from_address = request.form.get('from_address', '').strip()
            to_address = request.form.get('to_address', '').strip()
            if miles <= 0 and from_address and to_address:
                miles = estimate_miles(from_address, to_address)
            deduction = round(miles * IRS_MILEAGE_RATE, 2)
            conn.execute(
                'INSERT INTO mileage_entries (client_id, trip_date, from_address, to_address, purpose, miles, deduction) VALUES (?,?,?,?,?,?,?)',
                (client_id, request.form.get('trip_date', '').strip(), from_address, to_address, request.form.get('purpose', '').strip(), miles, deduction)
            )
            conn.commit()
            flash('Mileage entry saved.', 'success')
            return redirect(url_for('mileage', client_id=client_id))
        rows = conn.execute('SELECT * FROM mileage_entries WHERE client_id=? ORDER BY trip_date DESC, id DESC', (client_id,)).fetchall()
        client = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
    return render_template('mileage.html', mileage_entries=rows, client=client, client_id=client_id, home_address=DEFAULT_HOME_ADDRESS)



@app.route('/invoice-mileage', methods=['GET', 'POST'])
@login_required
def invoice_mileage():
    user = current_user()
    client_id = selected_client_id(user, 'post' if request.method == 'POST' else 'get')
    flash('Invoice mileage is now inside the Invoices tab.', 'success')
    return redirect(url_for('invoices', client_id=client_id))


@app.route('/other-expenses', methods=['GET', 'POST'])
@login_required
def other_expenses():
    user = current_user()
    client_id = selected_client_id(user, 'post' if request.method == 'POST' else 'get')

    with get_conn() as conn:
        client = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()

        if request.method == 'POST':
            expense_date = request.form.get('expense_date', '').strip() or date.today().isoformat()
            vendor_description = request.form.get('vendor_description', '').strip()
            category = request.form.get('category', 'other').strip().lower()
            amount = request.form.get('amount', type=float) or 0.0
            note = request.form.get('note', '').strip()

            if category not in other_expense_categories():
                category = 'other'

            if not vendor_description:
                flash('Enter a vendor or description.', 'error')
            elif amount <= 0:
                flash('Enter an amount greater than zero.', 'error')
            else:
                conn.execute(
                    'INSERT INTO other_expenses_entries (client_id, expense_date, vendor_description, category, amount, note) VALUES (?,?,?,?,?,?)',
                    (client_id, expense_date, vendor_description, category, amount, note)
                )
                conn.commit()
                flash('Expense saved.', 'success')
                return redirect(url_for('other_expenses', client_id=client_id))

        rows = conn.execute(
            'SELECT * FROM other_expenses_entries WHERE client_id=? ORDER BY expense_date DESC, id DESC',
            (client_id,)
        ).fetchall()
        summary_rows = conn.execute(
            'SELECT category, COUNT(*) entry_count, COALESCE(SUM(amount), 0) total_amount FROM other_expenses_entries WHERE client_id=? GROUP BY category ORDER BY LOWER(category)',
            (client_id,)
        ).fetchall()

    total_expenses = round(sum(float(row['amount'] or 0) for row in rows), 2)
    return render_template(
        'other_expenses.html',
        client=client,
        client_id=client_id,
        categories=other_expense_categories(),
        expense_entries=rows,
        expense_summary=summary_rows,
        total_expenses=total_expenses,
        today=date.today().isoformat(),
    )


@app.route('/reports')
@login_required
def reports():
    user = current_user()
    client_id = selected_client_id(user, 'get')
    report_type = request.args.get('report_type', 'summary')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    worker_id = request.args.get('worker_id', type=int)
    invoice_id = request.args.get('invoice_id', type=int)

    with get_conn() as conn:
        client = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
        workers = conn.execute('SELECT * FROM workers WHERE client_id=? ORDER BY CASE WHEN status="active" THEN 0 ELSE 1 END, name', (client_id,)).fetchall()
        invoices = conn.execute(
            "SELECT * FROM invoices WHERE client_id=? AND COALESCE(record_kind,'income_record')<>'estimate' ORDER BY job_number DESC, id DESC",
            (client_id,),
        ).fetchall()

        context = {
            'client': client,
            'workers': workers,
            'invoices': invoices,
            'client_id': client_id,
            'report_type': report_type,
            'start_date': start_date,
            'end_date': end_date,
            'worker_id': worker_id,
            'invoice_id': invoice_id,
            'summary': client_summary(client_id, start_date or None, end_date or None),
        }

        if report_type == 'workers':
            query = 'SELECT * FROM workers WHERE client_id=?'
            params = [client_id]
            if worker_id:
                query += ' AND id=?'
                params.append(worker_id)
            query += ' ORDER BY name'
            context['rows'] = conn.execute(query, tuple(params)).fetchall()
        elif report_type == 'payments':
            query = 'SELECT wp.*, w.name worker_name, w.worker_type FROM worker_payments wp JOIN workers w ON w.id=wp.worker_id WHERE w.client_id=?'
            params = [client_id]
            if worker_id:
                query += ' AND w.id=?'
                params.append(worker_id)
            clauses, more = between_clause('wp.payment_date', start_date or None, end_date or None)
            if clauses:
                query += ' AND ' + ' AND '.join(clauses)
                params += more
            query += ' ORDER BY wp.payment_date DESC'
            context['rows'] = conn.execute(query, tuple(params)).fetchall()
        elif report_type == 'invoices':
            query = "SELECT * FROM invoices WHERE client_id=? AND COALESCE(record_kind,'income_record')<>'estimate'"
            params = [client_id]
            if invoice_id:
                query += ' AND id=?'
                params.append(invoice_id)
            clauses, more = between_clause('invoice_date', start_date or None, end_date or None)
            if clauses:
                query += ' AND ' + ' AND '.join(clauses)
                params += more
            query += ' ORDER BY invoice_date DESC, id DESC'
            context['rows'] = conn.execute(query, tuple(params)).fetchall()
        elif report_type == 'gas':
            query = 'SELECT * FROM gas_entries WHERE client_id=?'
            params = [client_id]
            clauses, more = between_clause('week_start', start_date or None, end_date or None)
            if clauses:
                query += ' AND ' + ' AND '.join(clauses)
                params += more
            query += ' ORDER BY week_start DESC'
            context['rows'] = conn.execute(query, tuple(params)).fetchall()
        elif report_type == 'materials':
            query = 'SELECT * FROM materials WHERE client_id=?'
            params = [client_id]
            clauses, more = between_clause('material_date', start_date or None, end_date or None)
            if clauses:
                query += ' AND ' + ' AND '.join(clauses)
                params += more
            query += ' ORDER BY material_date DESC'
            context['rows'] = conn.execute(query, tuple(params)).fetchall()
        elif report_type == 'mileage':
            query = 'SELECT * FROM mileage_entries WHERE client_id=?'
            params = [client_id]
            clauses, more = between_clause('trip_date', start_date or None, end_date or None)
            if clauses:
                query += ' AND ' + ' AND '.join(clauses)
                params += more
            query += ' ORDER BY trip_date DESC'
            context['rows'] = conn.execute(query, tuple(params)).fetchall()
        else:
            context['rows'] = []

    return render_template('reports.html', **context)


@app.route('/payroll-tax', methods=['GET', 'POST'])
@admin_required
def payroll_tax():
    user = current_user()
    client_id = selected_client_id(user, 'post' if request.method == 'POST' else 'get')
    year = request.values.get('year', type=int) or date.today().year
    quarter = request.values.get('quarter', type=int) or ((date.today().month - 1) // 3 + 1)
    view = request.values.get('view', 'quarter')
    if request.method == 'POST' and request.form.get('action') == 'add_deposit':
        with get_conn() as conn:
            conn.execute('INSERT INTO payroll_tax_deposits (client_id, deposit_date, tax_year, tax_quarter, tax_month, amount, payment_method, confirmation_number, note) VALUES (?,?,?,?,?,?,?,?,?)', (
                client_id, request.form.get('deposit_date', '').strip(), year, quarter, request.form.get('tax_month', type=int) or quarter_months(quarter)[0], request.form.get('amount', type=float) or 0.0, request.form.get('payment_method', 'EFTPS').strip(), request.form.get('confirmation_number', '').strip(), request.form.get('note', '').strip()
            ))
            conn.commit()
        flash('Payroll tax deposit saved.', 'success')
        return redirect(url_for('payroll_tax', client_id=client_id, year=year, quarter=quarter, view=view))
    with get_conn() as conn:
        client = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
        w2_workers = conn.execute('SELECT * FROM workers WHERE client_id=? AND worker_type="W-2" ORDER BY name', (client_id,)).fetchall()
    summary = payroll_tax_summary(client_id, year, quarter)
    return render_template('payroll_tax.html', client=client, client_id=client_id, payroll_tax=summary, year=year, quarter=quarter, quarter_months=quarter_months(quarter), view=view, w2_workers=w2_workers, today=date.today().isoformat(), eftps_url=eftps_payment_url())


@app.route('/submit-for-cpa-review', methods=['POST'])
@login_required
def submit_for_cpa_review():
    user = current_user()
    if user['role'] != 'client':
        abort(403)
    client_id = selected_client_id(user, 'post')
    note = request.form.get('note', '').strip()
    with get_conn() as conn:
        latest = conn.execute('SELECT * FROM payroll_review_requests WHERE client_id=? ORDER BY id DESC LIMIT 1', (client_id,)).fetchone()
        if latest and latest['status'] == 'pending':
            flash('Already pending Administrator review.', 'error')
        else:
            conn.execute('INSERT INTO payroll_review_requests (client_id, submitted_by, status, note) VALUES (?,?,?,?)', (client_id, user['id'], 'pending', note))
            conn.execute('INSERT INTO internal_messages (client_id, sender_user_id, recipient_user_id, body, is_read) VALUES (?,?,?,?,0)', (client_id, user['id'], default_recipient_id(client_id, user), note or 'Submitted for Administrator review.'))
            conn.commit()
            flash('Submitted for Administrator review.', 'success')
    return redirect(url_for('dashboard', client_id=client_id))


@app.route('/review-request/<int:request_id>/<action>', methods=['POST'])
@admin_required
def review_request_action(request_id, action):
    if action not in {'approved', 'needs_correction'}:
        abort(400)
    user = current_user()
    review_note = request.form.get('review_note', '').strip()
    with get_conn() as conn:
        row = conn.execute('SELECT * FROM payroll_review_requests WHERE id=?', (request_id,)).fetchone()
        if not row:
            abort(404)
        conn.execute('UPDATE payroll_review_requests SET status=?, reviewed_by=?, reviewed_at=?, review_note=? WHERE id=?', (action, user['id'], datetime.now().isoformat(timespec='seconds'), review_note, request_id))
        if review_note:
            conn.execute('INSERT INTO internal_messages (client_id, sender_user_id, recipient_user_id, body, is_read) VALUES (?,?,?,?,0)', (row['client_id'], user['id'], default_recipient_id(row['client_id'], user), review_note))
        conn.commit()
    flash('Review updated.', 'success')
    return redirect(url_for('cpa_dashboard'))


@app.route('/chat', methods=['GET', 'POST'])
@login_required
def chat():
    user = current_user()
    client_id = selected_client_id(user, 'post' if request.method == 'POST' else 'get')
    if request.method == 'POST':
        body = request.form.get('body', '').strip()
        recipients = available_recipients(client_id, user['id'])
        valid_recipient_ids = {p['id'] for p in recipients}
        recipient_id = request.form.get('recipient_user_id', type=int) or default_recipient_id(client_id, user)
        if recipient_id not in valid_recipient_ids:
            recipient_id = default_recipient_id(client_id, user)
        if not recipients:
            flash('No available chat recipient is configured for this business yet.', 'error')
        elif body and recipient_id:
            with get_conn() as conn:
                conn.execute('INSERT INTO internal_messages (client_id, sender_user_id, recipient_user_id, body, is_read) VALUES (?,?,?,?,0)', (client_id, user['id'], recipient_id, body))
                conn.commit()
            flash('Message sent.', 'success')
        else:
            flash('Enter a message before sending.', 'error')
        return_path = request.form.get('return_path', '').strip()
        if return_path.startswith('/') and '://' not in return_path and not return_path.startswith('//'):
            return redirect(return_path)
        return_to = request.form.get('return_to', '').strip()
        if return_to == 'dashboard':
            return redirect(url_for('dashboard', client_id=client_id))
        if return_to == 'cpa_dashboard':
            return redirect(url_for('cpa_dashboard', client_id=client_id))
        return redirect(url_for('chat', client_id=client_id))
    with get_conn() as conn:
        client = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
    mark_messages_read(client_id, user['id'])
    return render_template('chat.html', client=client, client_id=client_id, messages=chat_messages(client_id), participants=chat_participants(client_id), review_request=latest_review_request(client_id), chat_unread_count=unread_message_count(client_id, user['id']), chat_recipients=available_recipients(client_id, user['id']), selected_recipient_id=default_recipient_id(client_id, user), latest_incoming_message=latest_incoming_message(client_id, user['id']))



@app.route('/admin/worker-portal-approval', methods=['POST'])
@admin_required
def admin_worker_portal_approval():
    worker_id = request.form.get('worker_id', type=int)
    decision = request.form.get('decision', 'approve').strip().lower()
    if decision not in {'approve', 'needs_correction'}:
        decision = 'approve'
    with get_conn() as conn:
        worker = conn.execute('SELECT * FROM workers WHERE id=?', (worker_id,)).fetchone() if worker_id else None
        if not worker:
            flash('Worker portal request not found.', 'error')
            return redirect(url_for('cpa_dashboard'))
        if decision == 'approve':
            approved_at = datetime.now().isoformat(timespec='seconds')
            conn.execute("UPDATE workers SET portal_approval_status=?, portal_requested_at=COALESCE(NULLIF(portal_requested_at,''), ?), portal_approved_at=?, portal_approved_by=?, portal_access_enabled=1 WHERE id=?", ('approved', approved_at, approved_at, current_user()['id'], worker_id))
            client_row = conn.execute('SELECT business_name FROM clients WHERE id=?', (worker['client_id'],)).fetchone()
            welcome_sent = False
            welcome_error = ''
            if (worker['email'] or '').strip() and smtp_email_ready():
                try:
                    send_welcome_email(
                        (worker['email'] or '').strip().lower(),
                        worker['name'],
                        'worker',
                        login_path='/worker-login',
                        business_name=(client_row['business_name'] if client_row else '')
                    )
                    welcome_sent = True
                except Exception as e:
                    welcome_error = str(e)[:200]
            if welcome_sent:
                flash('Worker portal access approved. Welcome email sent.', 'success')
            elif smtp_email_ready() and (worker['email'] or '').strip():
                flash(f'Worker portal access approved, but welcome email failed: {welcome_error}', 'error')
            else:
                flash('Worker portal access approved.', 'success')
        else:
            conn.execute('UPDATE workers SET portal_approval_status=?, portal_access_enabled=0 WHERE id=?', ('needs_correction', worker_id))
            flash('Worker portal request marked for correction.', 'success')
        conn.commit()
    return redirect(url_for('cpa_dashboard', client_id=worker['client_id']))


@app.route('/work-schedule', methods=['GET', 'POST'])
@login_required
def work_schedule():
    user = current_user()
    client_id = selected_client_id(user, 'post' if request.method == 'POST' else 'get')
    prefill_contact_id = request.values.get('customer_contact_id', type=int)
    with get_conn() as conn:
        client = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
        ensure_recurring_schedule_entries(conn, client_id=client_id, actor_user_id=user['id'])
        conn.commit()
        workers = conn.execute('SELECT id, name, status FROM workers WHERE client_id=? ORDER BY CASE WHEN status="active" THEN 0 ELSE 1 END, name', (client_id,)).fetchall()
        customer_contact_rows = conn.execute(
            '''SELECT *
               FROM customer_contacts
               WHERE client_id=? AND COALESCE(status,'active')='active'
               ORDER BY LOWER(customer_name), id DESC''',
            (client_id,),
        ).fetchall()
        customer_contact_lookup = {row['id']: row for row in customer_contact_rows}
        prefill_contact = customer_contact_lookup.get(prefill_contact_id)
        valid_worker_ids = {int(w['id']) for w in workers}
        worker_names_by_id = {int(w['id']): w['name'] for w in workers}
        if request.method == 'POST':
            action = request.form.get('action', 'add_schedule').strip()
            if action == 'delete_schedule':
                schedule_id = request.form.get('schedule_id', type=int)
                conn.execute('DELETE FROM work_schedule_entries WHERE id=? AND client_id=?', (schedule_id, client_id))
                conn.commit()
                flash('Schedule entry removed.', 'success')
                return redirect(url_for('work_schedule', client_id=client_id))
            assigned_ids = [wid for wid in normalize_worker_assignment_ids(request.form.getlist('assigned_worker_ids')) if wid in valid_worker_ids]
            job_name = request.form.get('job_name', '').strip()
            schedule_date = request.form.get('schedule_date', '').strip()
            if not job_name:
                flash('Job name is required.', 'error')
            elif not schedule_date:
                flash('Date is required.', 'error')
            else:
                assigned_names = ', '.join(worker_names_by_id[wid] for wid in assigned_ids if wid in worker_names_by_id)
                conn.execute(
                    '''INSERT INTO work_schedule_entries (
                        client_id, customer_contact_id, job_name, job_address, scope_of_work, schedule_date,
                        start_time, end_time, estimated_duration, assigned_worker_ids,
                        assigned_worker_names, notes, created_by_user_id
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (
                        client_id,
                        request.form.get('customer_contact_id', type=int),
                        job_name,
                        request.form.get('job_address', '').strip(),
                        request.form.get('scope_of_work', '').strip(),
                        schedule_date,
                        request.form.get('start_time', '').strip(),
                        request.form.get('end_time', '').strip(),
                        request.form.get('estimated_duration', '').strip(),
                        assigned_worker_token(assigned_ids),
                        assigned_names,
                        request.form.get('notes', '').strip(),
                        user['id'],
                    )
                )
                conn.commit()
                flash('Work schedule entry saved.', 'success')
                return redirect(url_for('work_schedule', client_id=client_id))
        entries = conn.execute(
            '''SELECT ws.*
               FROM work_schedule_entries ws
               WHERE ws.client_id=?
               ORDER BY ws.schedule_date ASC,
                        CASE WHEN COALESCE(ws.start_time,'')='' THEN 1 ELSE 0 END,
                        ws.start_time ASC,
                        ws.id DESC''',
            (client_id,)
        ).fetchall()
    upcoming_entries = [row for row in entries if (row['schedule_date'] or '') >= date.today().isoformat()]
    return render_template(
        'work_schedule.html',
        client=client,
        client_id=client_id,
        workers=workers,
        customer_contacts=[dict(row) for row in customer_contact_rows],
        prefill_contact_id=(prefill_contact['id'] if prefill_contact else None),
        prefill_contact=dict(prefill_contact) if prefill_contact else None,
        entries=entries,
        upcoming_entries=upcoming_entries,
        today=date.today().isoformat(),
    )


@app.route('/worker-portal/schedule')
@worker_login_required
def worker_schedule():
    worker = current_worker()
    entries = worker_schedule_rows_for_worker(worker['id'], worker['client_id'])
    summary = worker_schedule_summary(entries)
    from datetime import date
    import calendar as pycal

    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    today = date.today()
    if not year or not month:
        if summary.get('next_item') and summary['next_item']['schedule_date']:
            try:
                first_date = date.fromisoformat(summary['next_item']['schedule_date'])
                year, month = first_date.year, first_date.month
            except ValueError:
                year, month = today.year, today.month
        else:
            year, month = today.year, today.month

    month_entries = [row for row in entries if (row['schedule_date'] or '').startswith(f"{year:04d}-{month:02d}-")]
    entries_by_day = {}
    for row in month_entries:
        entries_by_day.setdefault(row['schedule_date'], []).append(row)

    cal = pycal.Calendar(firstweekday=0)
    weeks = list(cal.monthdatescalendar(year, month))
    prev_month = month - 1
    prev_year = year
    if prev_month == 0:
        prev_month = 12
        prev_year -= 1
    next_month = month + 1
    next_year = year
    if next_month == 13:
        next_month = 1
        next_year += 1

    return render_template(
        'worker_schedule.html',
        worker=worker,
        entries=entries,
        schedule_summary=summary,
        unread_count=worker_unread_message_count(worker['id']),
        year=year,
        month=month,
        month_name=pycal.month_name[month],
        weeks=weeks,
        entries_by_day=entries_by_day,
        today=today.isoformat(),
        prev_year=prev_year,
        prev_month=prev_month,
        next_year=next_year,
        next_month=next_month,
    )



@app.route('/worker-portal')
@worker_login_required
def worker_portal():
    return redirect(url_for('worker_time_summary'))


@app.route('/worker-portal/time-summary')
@worker_login_required
def worker_time_summary():
    worker = current_worker()
    summary = worker_time_summary_data(worker['id'])
    pay_summary = worker_payments_summary(worker['id'])
    return render_template('worker_time_summary.html', worker=worker, summary=summary, pay_summary=pay_summary)


@app.route('/worker-portal/pay-stubs')
@worker_login_required
def worker_pay_stubs():
    worker = current_worker()
    with get_conn() as conn:
        payments = conn.execute('SELECT * FROM worker_payments WHERE worker_id=? ORDER BY payment_date DESC, id DESC', (worker['id'],)).fetchall()
    pay_summary = worker_payments_summary(worker['id'])
    payment_method_labels = worker_payment_method_label_map()
    payment_status_labels = worker_payment_status_label_map()
    return render_template(
        'worker_pay_stubs_v2.html',
        worker=worker,
        payments=payments,
        pay_summary=pay_summary,
        payment_method_labels=payment_method_labels,
        payment_status_labels=payment_status_labels,
    )


@app.route('/worker-portal/pay-stubs/<int:payment_id>')
@worker_login_required
def worker_pay_stub_detail(payment_id):
    worker = current_worker()
    with get_conn() as conn:
        payment = conn.execute('SELECT * FROM worker_payments WHERE id=? AND worker_id=?', (payment_id, worker['id'])).fetchone()
    if not payment:
        abort(404)
    stub = worker_payment_stub_context(worker, payment)
    return render_template('worker_pay_stub_detail_v2.html', worker=worker, payment=payment, stub=stub)


@app.route('/worker-portal/messages', methods=['GET', 'POST'])
@worker_login_required
def worker_messages():
    worker = current_worker()
    manager = primary_manager_user(worker['client_id'])
    if request.method == 'POST':
        body = request.form.get('body', '').strip()
        if body:
            with get_conn() as conn:
                conn.execute(
                    'INSERT INTO worker_messages (worker_id, sender_kind, sender_user_id, body, is_read_worker, is_read_manager) VALUES (?,?,?,?,?,?)',
                    (worker['id'], 'worker', None, body, 1, 0)
                )
                conn.commit()
            flash('Message sent.', 'success')
            return_path = request.form.get('return_path', '').strip()
            if return_path.startswith('/') and '://' not in return_path and not return_path.startswith('//'):
                return redirect(return_path)
            return redirect(url_for('worker_messages'))
        flash('Enter a message before sending.', 'error')
    mark_worker_messages_read(worker['id'])
    rows = worker_message_rows(worker['id'])
    return render_template('worker_messages_v2.html', worker=worker, manager=manager, messages=rows, unread_count=worker_unread_message_count(worker['id']))


@app.route('/worker-portal/time-off', methods=['GET', 'POST'])
@worker_login_required
def worker_time_off():
    worker = current_worker()
    if request.method == 'POST':
        start_date = request.form.get('start_date', '').strip()
        end_date = request.form.get('end_date', '').strip()
        request_type = request.form.get('request_type', 'Day Off').strip() or 'Day Off'
        note = request.form.get('note', '').strip()
        if not start_date:
            flash('Start date is required.', 'error')
        else:
            if not end_date:
                end_date = start_date
            with get_conn() as conn:
                conn.execute(
                    'INSERT INTO worker_time_off_requests (worker_id, request_type, start_date, end_date, note, status) VALUES (?,?,?,?,?,?)',
                    (worker['id'], request_type[:50], start_date, end_date, note[:1000], 'pending')
                )
                conn.commit()
            flash('Time-off request submitted.', 'success')
            return redirect(url_for('worker_time_off'))
    requests = worker_time_off_rows(worker['id'])
    return render_template('worker_time_off.html', worker=worker, requests=requests, unread_count=worker_unread_message_count(worker['id']))


@app.route('/worker-portal/notices')
@worker_login_required
def worker_notices():
    worker = current_worker()
    custom_notices = [row for row in business_policy_notices(worker['client_id']) if int(row['is_active'] or 0) == 1]
    return render_template(
        'worker_notices.html',
        worker=worker,
        notice_sections=default_worker_notice_sections(),
        custom_notices=custom_notices,
        unread_count=worker_unread_message_count(worker['id'])
    )


@app.route('/irs-tips')
@login_required
def irs_tips():
    return render_template('irs_tips.html')


@app.route('/help-center', methods=['GET', 'POST'])
@login_required
def help_center():
    user = current_user()
    client = None
    recent_request = None

    if user['role'] != 'admin':
        client_id = selected_client_id(user, 'post' if request.method == 'POST' else 'get')
        with get_conn() as conn:
            client = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
            if request.method == 'POST':
                request_type = request.form.get('request_type', '').strip()
                message = request.form.get('message', '').strip()
                if request_type not in business_help_request_types():
                    request_type = 'Suggestion'
                if message:
                    conn.execute(
                        'INSERT INTO business_help_requests (client_id, submitted_by_user_id, request_type, message) VALUES (?,?,?,?)',
                        (client_id, user['id'], request_type, message)
                    )
                    conn.commit()
                    flash('Your request was submitted successfully.', 'success')
                    return redirect(url_for('help_center', client_id=client_id))
                flash('Enter your suggestion or request before submitting.', 'error')
            recent_request = conn.execute(
                'SELECT * FROM business_help_requests WHERE client_id=? AND submitted_by_user_id=? ORDER BY id DESC LIMIT 1',
                (client_id, user['id'])
            ).fetchone()

    return render_template(
        'help_center.html',
        client=client,
        request_type_options=business_help_request_types(),
        recent_request=recent_request,
    )


@app.route('/forms/w4/<int:worker_id>', methods=['GET', 'POST'])
@login_required
def w4(worker_id):
    user = current_user()
    with get_conn() as conn:
        worker = conn.execute('SELECT * FROM workers WHERE id=?', (worker_id,)).fetchone()
        if not worker or not allowed_client(user, worker['client_id']):
            abort(403)
        if request.method == 'POST':
            existing = conn.execute('SELECT id FROM w4_answers WHERE worker_id=?', (worker_id,)).fetchone()
            data = (
                request.form.get('filing_status', ''),
                1 if request.form.get('multiple_jobs') else 0,
                request.form.get('qualifying_children', type=float) or 0,
                request.form.get('other_dependents', type=float) or 0,
                request.form.get('other_income', type=float) or 0,
                request.form.get('deductions', type=float) or 0,
                request.form.get('extra_withholding', type=float) or 0,
                request.form.get('signature_name', '').strip(),
                request.form.get('signed_date', '').strip(),
                datetime.now().isoformat(timespec='seconds'),
            )
            if existing:
                conn.execute('UPDATE w4_answers SET filing_status=?, multiple_jobs=?, qualifying_children=?, other_dependents=?, other_income=?, deductions=?, extra_withholding=?, signature_name=?, signed_date=?, updated_at=? WHERE worker_id=?', data + (worker_id,))
            else:
                conn.execute('INSERT INTO w4_answers (filing_status, multiple_jobs, qualifying_children, other_dependents, other_income, deductions, extra_withholding, signature_name, signed_date, updated_at, worker_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)', data + (worker_id,))
            conn.commit()
            flash('W-4 answers saved.', 'success')
            return redirect(url_for('w4', worker_id=worker_id))
        answers = conn.execute('SELECT * FROM w4_answers WHERE worker_id=?', (worker_id,)).fetchone()
    return render_template('w4.html', worker=worker, answers=answers)


@app.route('/forms/w2/<int:worker_id>')
@login_required
def w2(worker_id):
    year = request.args.get('year', type=int) or date.today().year
    user = current_user()
    with get_conn() as conn:
        worker = conn.execute('SELECT * FROM workers WHERE id=?', (worker_id,)).fetchone()
        if not worker or not allowed_client(user, worker['client_id']):
            abort(403)
        payments = conn.execute('SELECT * FROM worker_payments WHERE worker_id=? AND substr(payment_date,1,4)=? ORDER BY payment_date', (worker_id, str(year))).fetchall()
        client = conn.execute('SELECT * FROM clients WHERE id=?', (worker['client_id'],)).fetchone()
    payer = payer_profile_for_client(client)
    return render_template('w2.html', worker=worker, payments=payments, year=year, totals=worker_year_totals(worker_id, year), **payer)


@app.route('/forms/1099/<int:worker_id>')
@login_required
def form_1099(worker_id):
    year = request.args.get('year', type=int) or date.today().year
    user = current_user()
    with get_conn() as conn:
        worker = conn.execute('SELECT * FROM workers WHERE id=?', (worker_id,)).fetchone()
        if not worker or not allowed_client(user, worker['client_id']):
            abort(403)
        payments = conn.execute('SELECT * FROM worker_payments WHERE worker_id=? AND substr(payment_date,1,4)=? ORDER BY payment_date', (worker_id, str(year))).fetchall()
        client = conn.execute('SELECT * FROM clients WHERE id=?', (worker['client_id'],)).fetchone()
    payer = payer_profile_for_client(client)
    return render_template('1099.html', worker=worker, payments=payments, year=year, totals=worker_year_totals(worker_id, year), **payer)


init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', '5000'))
    app.run(host='0.0.0.0', port=port, debug=False)
