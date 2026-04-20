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
from cryptography.fernet import Fernet
import base64
import hashlib
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, datetime, timedelta
from pathlib import Path
from functools import wraps, lru_cache
from urllib.parse import urlparse
from urllib import request as urlrequest, error as urlerror

from geopy.distance import geodesic
from geopy.geocoders import Nominatim

from flask import Flask, render_template, render_template_string, request, redirect, url_for, session, flash, abort, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get('DATA_DIR', str(BASE_DIR / 'data')))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(os.environ.get('DATABASE_PATH', str(DATA_DIR / 'rds_core_web.db')))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
EMAIL_CONFIG_PATH = DATA_DIR / 'email_runtime_config.json'

APP_NAME = 'LedgerFlow'
APP_SUBTITLE = 'Financial control for growing service businesses'
BRAND_TAGLINE = 'Financial control for growing service businesses.'
BRAND_LOGO_FILENAME = 'ledgerflow-logo.png'
BRAND_MARK_FILENAME = 'ledgerflow-mark.png'
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
    translated = TRANSLATIONS.get(source, {}).get(normalize_language(lang), source)
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
            'label': 'Trial Invite Sent' if is_trial else 'Invite Sent',
            'detail': (
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
    with_link = sum(1 for row in open_rows if fee_collection_guidance(row)['url'])
    manual = sum(1 for row in open_rows if normalize_collection_method(row['collection_method'] or default_collection_method()) in {'manual_offline', 'zelle_manual'})
    request_based = sum(1 for row in open_rows if normalize_collection_method(row['collection_method'] or default_collection_method()) == 'send_payment_request')
    charge_on_file = sum(1 for row in open_rows if normalize_collection_method(row['collection_method'] or default_collection_method()) == 'charge_saved_method')
    parts = []
    if with_link:
        parts.append(f'{with_link} ready to pay online')
    if manual:
        parts.append(f'{manual} using instructions')
    if request_based:
        parts.append(f'{request_based} waiting on request delivery')
    if charge_on_file:
        parts.append(f'{charge_on_file} marked for method-on-file collection')
    return {
        'headline': f'{len(open_rows)} open administrator fee{"s" if len(open_rows) != 1 else ""}',
        'detail': ', '.join(parts) + '.' if parts else 'Review the fee actions below to complete payment.',
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


def send_trial_invite_email(to_email: str, to_name: str, business_name: str, invite_link: str, trial_days: int = 0):
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
    video_preview_html = (
        f"<div style='margin-top:20px;padding:18px 20px;border:1px solid #d7dce7;border-radius:18px;background:#ffffff'>"
        f"<div style='color:#141b2d;font-size:14px;font-weight:800'>Welcome tutorial preview</div>"
        f"<div style='margin-top:12px;display:flex;align-items:center;justify-content:center;min-height:160px;border-radius:16px;border:1px dashed #c9d2e0;background:linear-gradient(180deg,#f7f9fc,#eef2f6);color:#425067;font-size:14px;font-weight:700;text-align:center;padding:18px'>"
        f"Video-ready trial introduction<br>Open the trial page to watch the welcome walkthrough"
        f"</div>"
        f"<div style='margin-top:10px;color:#5b687d;font-size:13px;line-height:1.7'>Email clients do not reliably play embedded video, so this preview block takes the business directly into the full trial page where the welcome tutorial and setup guidance live together.</div>"
        f"</div>"
    )
    trial_summary_html = (
        video_preview_html +
        f"<div style='margin-top:22px;padding:18px 20px;border:1px solid #d7dce7;border-radius:18px;background:#f7f1e7'>"
        f"<div style='color:#141b2d;font-size:13px;font-weight:800;letter-spacing:.08em;text-transform:uppercase'>Complimentary Trial Offer</div>"
        f"<div style='margin-top:8px;color:#141b2d;font-size:24px;line-height:1.25;font-weight:800'>{trial_days}-day free guided trial</div>"
        f"<div style='margin-top:10px;color:#48546a;font-size:14px;line-height:1.7'>Review the subscription options below, create your secure login, and complete setup when you are ready. Billing begins only after the complimentary trial window ends.</div>"
        f"</div>"
        f"<div style='margin-top:18px;padding:18px 20px;border:1px solid #dbe3ef;border-radius:18px;background:#ffffff'>"
        f"<div style='color:#141b2d;font-size:14px;font-weight:800;margin-bottom:12px'>Subscription options preview</div>"
        f"<table role='presentation' style='width:100%;border-collapse:collapse'>"
        f"<tr><th align='left' style='padding:0 12px 10px 12px;color:#74829b;font-size:12px;letter-spacing:.08em;text-transform:uppercase'>Tier</th><th align='left' style='padding:0 12px 10px 12px;color:#74829b;font-size:12px;letter-spacing:.08em;text-transform:uppercase'>Price</th><th align='left' style='padding:0 12px 10px 12px;color:#74829b;font-size:12px;letter-spacing:.08em;text-transform:uppercase'>Designed For</th></tr>"
        f"{''.join(tier_rows)}"
        f"</table>"
        f"</div>"
    )
    body = "\n".join([
        greeting,
        "",
        f"You've been invited to try LedgerFlow with a {trial_days}-day complimentary business trial for {business_name}.",
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
        cta_link=invite_link,
        detail_rows=[
            ('Business', business_name),
            ('Trial Offer', f'{trial_days} complimentary days'),
            ('Invite Email', to_email),
        ],
        feature_tags=['7-Day Trial', 'Subscription Options', 'Guided Setup', 'Video Walkthrough Space'],
        support_note='If you were not expecting this invitation, you can ignore this email.',
        extra_sections_html=trial_summary_html,
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


def smtp_email_ready() -> bool:
    cfg = smtp_config()
    return bool(cfg['sender_email'] and cfg['smtp_username'] and cfg['smtp_password'])


def render_marketing_email(*, eyebrow: str, title: str, intro: str, greeting: str, body_lines: list[str], cta_label: str = '', cta_link: str = '', detail_rows: list[tuple[str, str]] | None = None, feature_tags: list[str] | None = None, support_note: str = '', extra_sections_html: str = '') -> str:
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


def log_email_delivery(*, client_id=None, email_type='', recipient_email='', recipient_name='', subject='', body_text='', body_html='', status='sent', error_message='', created_by_user_id=None, related_invite_id=None, related_user_id=None):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO email_delivery_log
               (client_id, email_type, recipient_email, recipient_name, subject, body_text, body_html, status, error_message, created_by_user_id, related_invite_id, related_user_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
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
            )
        )
        conn.commit()


def now_iso() -> str:
    return datetime.now().isoformat(timespec='seconds')


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
                client_name TEXT NOT NULL,
                client_address TEXT,
                paid_amount REAL DEFAULT 0,
                invoice_date TEXT,
                notes TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
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
        ensure_column(conn, 'clients', 'business_type', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'business_category', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'business_specialty', "TEXT DEFAULT ''")
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
        ensure_column(conn, 'clients', 'trial_offer_days', 'INTEGER NOT NULL DEFAULT 0')
        ensure_column(conn, 'clients', 'trial_started_at', "TEXT DEFAULT ''")
        ensure_column(conn, 'clients', 'trial_ends_at', "TEXT DEFAULT ''")
        ensure_column(conn, 'invoices', 'notes', "TEXT DEFAULT ''")
        ensure_column(conn, 'invoices', 'income_category', "TEXT DEFAULT 'service_income'")
        ensure_column(conn, 'invoices', 'sales_tax_amount', 'REAL NOT NULL DEFAULT 0')
        ensure_column(conn, 'invoices', 'sales_tax_paid', 'INTEGER NOT NULL DEFAULT 0')

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
            flash('Team member portal access is no longer active.', 'error')
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


def current_language_code(user=None, worker=None) -> str:
    session_lang = normalize_language(session.get('preferred_language', ''))
    if session_lang != 'en' or session.get('preferred_language'):
        return session_lang
    if worker and (worker['preferred_language'] or '').strip():
        return normalize_language(worker['preferred_language'])
    if user and (user['preferred_language'] or '').strip():
        return normalize_language(user['preferred_language'])
    return 'en'


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
        inv_where = ['client_id=?']
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
        return conn.execute(
            '''SELECT ws.*
               FROM work_schedule_entries ws
               WHERE ws.client_id=?
               ORDER BY ws.schedule_date ASC,
                        CASE WHEN COALESCE(ws.start_time,'')='' THEN 1 ELSE 0 END,
                        ws.start_time ASC,
                        ws.id DESC''',
            (client_id,)
        ).fetchall()


def worker_schedule_rows_for_worker(worker_id: int, client_id: int):
    token = f'%,{worker_id},%'
    with get_conn() as conn:
        return conn.execute(
            '''SELECT ws.*
               FROM work_schedule_entries ws
               WHERE ws.client_id=?
                 AND COALESCE(ws.assigned_worker_ids,'') LIKE ?
               ORDER BY ws.schedule_date ASC,
                        CASE WHEN COALESCE(ws.start_time,'')='' THEN 1 ELSE 0 END,
                        ws.start_time ASC,
                        ws.id DESC''',
            (client_id, token)
        ).fetchall()


def worker_schedule_summary(rows):
    today_iso = date.today().isoformat()
    upcoming = [row for row in rows if (row['schedule_date'] or '') >= today_iso]
    next_item = upcoming[0] if upcoming else (rows[0] if rows else None)
    return {
        'total_items': len(rows),
        'upcoming_count': len(upcoming),
        'next_item': next_item,
    }


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
    if request.endpoint in {'clients', 'client_users', 'cpa_dashboard', 'admin_calendar', 'admin_tasks', 'email_settings', 'ai_guide_settings'}:
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
    current_language = current_language_code(user, worker)
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
        flash(f'Language saved: {dict(LANGUAGE_OPTIONS).get(language, "English")}.', 'success')
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
                    flash('Full name is required.', 'error')
                elif not email:
                    flash('Email is required.', 'error')
                elif len(password) < 8:
                    flash('Password must be at least 8 characters.', 'error')
                elif password != confirm_password:
                    flash('Passwords do not match.', 'error')
                else:
                    with get_conn() as conn:
                        if conn.execute("SELECT 1 FROM users WHERE lower(email)=?", (email,)).fetchone():
                            flash('Email already exists.', 'error')
                        else:
                            conn.execute(
                                'INSERT INTO users (email, password_hash, full_name, role, client_id, preferred_language) VALUES (?,?,?,?,?,?)',
                                (email, generate_password_hash(password), full_name, 'admin', None, selected_language)
                            )
                            conn.commit()
                            flash('Administrator account created. Sign in below.', 'success')
                            return redirect(url_for('login'))
        else:
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            with get_conn() as conn:
                user = conn.execute('SELECT * FROM users WHERE lower(email)=?', (email,)).fetchone()
                if user and check_password_hash(user['password_hash'], password):
                    session.clear()
                    session['user_id'] = user['id']
                    session['preferred_language'] = normalize_language(user['preferred_language'] or selected_language)
                    if user['role'] == 'client' and user_requires_business_onboarding(user):
                        return redirect(url_for('business_onboarding'))
                    if user['role'] == 'client':
                        issue = client_access_issue_for_user(user)
                        if issue:
                            return redirect(url_for('business_comeback'))
                        client = conn.execute('SELECT id, trial_offer_days FROM clients WHERE id=?', (user['client_id'],)).fetchone()
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
                flash('Worker portal access is pending administrator approval.', 'error')
            elif has_needs_correction and not has_approved:
                flash('Worker portal access needs correction from the business before you can sign in.', 'error')
            elif has_terminated and not has_approved:
                flash('Team member portal access is no longer active.', 'error')
            else:
                flash('Invalid email or password.', 'error')
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
                flash('Team member portal access is pending administrator approval.', 'error')
            elif has_needs_correction and not has_approved:
                flash('Team member portal access needs correction before you can sign in.', 'error')
            elif has_terminated and not has_approved:
                flash('Team member portal access is no longer active.', 'error')
            else:
                flash('Invalid team member email or password.', 'error')
    return render_template('worker_login.html')


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
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
        flash(f'If the email exists in {APP_NAME}, a password reset request has been submitted. Check your email if delivery is enabled, or contact your administrator.', 'success')
        return redirect(url_for('forgot_password'))
    return render_template('forgot_password.html')


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    with get_conn() as conn:
        reset_row = conn.execute(
            "SELECT * FROM password_reset_requests WHERE token=? AND status='pending' ORDER BY id DESC LIMIT 1",
            (token,)
        ).fetchone()
        if not reset_row:
            flash('This reset link is invalid or has already been used.', 'error')
            return redirect(url_for('forgot_password'))
        try:
            expires_at = datetime.fromisoformat((reset_row['expires_at'] or '').replace('Z', ''))
        except Exception:
            expires_at = None
        if not expires_at or expires_at < datetime.utcnow():
            conn.execute("UPDATE password_reset_requests SET status='expired' WHERE id=?", (reset_row['id'],))
            conn.commit()
            flash('This reset link has expired. Submit a new reset request.', 'error')
            return redirect(url_for('forgot_password'))

        if request.method == 'POST':
            password = request.form.get('password', '').strip()
            confirm_password = request.form.get('confirm_password', '').strip()
            if len(password) < 8:
                flash('Password must be at least 8 characters.', 'error')
            elif password != confirm_password:
                flash('Passwords do not match.', 'error')
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
                flash('Password reset complete. Sign in with your new password.', 'success')
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
        invoices = conn.execute('SELECT * FROM invoices WHERE client_id=? ORDER BY invoice_date DESC, id DESC LIMIT 10', (client_id,)).fetchall()
        workers = conn.execute('SELECT * FROM workers WHERE client_id=? ORDER BY CASE WHEN status="active" THEN 0 ELSE 1 END, name', (client_id,)).fetchall()
    mark_messages_read(client_id, user['id'])
    payment_summary = business_payment_summary(client_id)
    open_admin_fee_rows = [row for row in payment_summary['rows'] if (row['status'] or 'pending') in {'pending', 'processing'}]
    with get_conn() as conn:
        payment_methods = conn.execute(
            '''SELECT *
               FROM business_payment_methods
               WHERE client_id=?
               ORDER BY is_default DESC, is_backup DESC, updated_at DESC, id DESC''',
            (client_id,),
        ).fetchall()
    return render_template('dashboard.html', client=client, invoices=invoices, workers=workers, summary=client_summary(client_id), client_id=client_id, review_request=latest_review_request(client_id), chat_rows=chat_messages(client_id), chat_unread_count=unread_message_count(client_id, user['id']), chat_recipients=available_recipients(client_id, user['id']), selected_recipient_id=default_recipient_id(client_id, user), latest_incoming_message=latest_incoming_message(client_id, user['id']), admin_fee_summary=payment_summary, open_admin_fee_rows=open_admin_fee_rows, open_fee_guidance=open_fee_guidance(open_admin_fee_rows), payment_method_summary=payment_method_summary(payment_methods), subscription_status_labels=subscription_status_label_map())


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
        invoices = conn.execute('SELECT * FROM invoices WHERE client_id=? ORDER BY invoice_date DESC LIMIT 8', (client_id,)).fetchall()
        mileage = conn.execute('SELECT * FROM mileage_entries WHERE client_id=? ORDER BY trip_date DESC LIMIT 8', (client_id,)).fetchall()
    return render_template('summary.html', client=client, client_id=client_id, workers=workers, invoices=invoices, mileage_entries=mileage, summary=client_summary(client_id, start_date or None, end_date or None), start_date=start_date, end_date=end_date)


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
                rejoin_email = (existing['email'] or '').strip().lower()
                rejoin_name = (existing['contact_name'] or '').strip()
                if not rejoin_email:
                    flash('Add a business email before sending a rejoin invite.', 'error')
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
            values = (
                business_name,
                business_structure,
                business_category,
                business_specialty,
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
                    'UPDATE clients SET business_name=?, business_type=?, business_category=?, business_specialty=?, service_level=?, access_service_level=?, access_override_note=?, subscription_plan_code=?, subscription_status=?, subscription_amount=?, subscription_interval=?, subscription_autopay_enabled=?, subscription_next_billing_date=?, subscription_started_at=?, subscription_canceled_at=?, subscription_paused_at=?, default_payment_method_label=?, default_payment_method_status=?, backup_payment_method_label=?, billing_notes=?, contact_name=?, phone=?, email=?, address=?, ein=?, eftps_status=?, eftps_login_reference=?, filing_type=?, bank_name=?, bank_account_nickname=?, bank_account_last4=?, bank_account_holder_name=?, bank_account_number=?, bank_routing_number=?, credit_card_nickname=?, credit_card_last4=?, credit_card_holder_name=?, credit_card_number=?, payroll_contact_name=?, payroll_contact_phone=?, payroll_contact_email=?, state_tax_id=?, record_status=?, archive_reason=?, archived_at=?, archived_by_user_id=?, reactivated_at=?, updated_at=?, updated_by_user_id=? WHERE id=?',
                    values + (now_value, user['id'], client_id)
                )
                log_client_profile_history(conn, client_id=client_id, action='updated', changed_by_user_id=user['id'])
                conn.commit()
                flash('Business profile updated.', 'success')
                return redirect(url_for('clients'))
            conn.execute(
                f'INSERT INTO clients (business_name, business_type, business_category, business_specialty, service_level, access_service_level, access_override_note, subscription_plan_code, subscription_status, subscription_amount, subscription_interval, subscription_autopay_enabled, subscription_next_billing_date, subscription_started_at, subscription_canceled_at, subscription_paused_at, default_payment_method_label, default_payment_method_status, backup_payment_method_label, billing_notes, contact_name, phone, email, address, ein, eftps_status, eftps_login_reference, filing_type, bank_name, bank_account_nickname, bank_account_last4, bank_account_holder_name, bank_account_number, bank_routing_number, credit_card_nickname, credit_card_last4, credit_card_holder_name, credit_card_number, payroll_contact_name, payroll_contact_phone, payroll_contact_email, state_tax_id, record_status, archive_reason, archived_at, archived_by_user_id, reactivated_at, created_by_user_id, updated_at, updated_by_user_id) VALUES ({",".join(["?"] * 50)})',
                values + (user['id'], now_value, user['id'])
            )
            client_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            log_client_profile_history(conn, client_id=client_id, action='created', changed_by_user_id=user['id'])
            conn.commit()
            flash('Business profile created.', 'success')
            return redirect(url_for('clients'))
        if user['role'] == 'admin':
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
            row = conn.execute(
                """SELECT c.*, creator.full_name created_by_name, updater.full_name updated_by_name
                   FROM clients c
                   LEFT JOIN users creator ON creator.id = c.created_by_user_id
                   LEFT JOIN users updater ON updater.id = c.updated_by_user_id
                   WHERE c.id=?""",
                (user['client_id'],)
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
        is_admin=(user['role']=='admin'),
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
                    conn.execute(
                        'INSERT INTO users (email, password_hash, full_name, role, client_id) VALUES (?,?,?,?,?)',
                        (email, generate_password_hash(password), full_name, 'client', client_id)
                    )
                    business = conn.execute('SELECT business_name FROM clients WHERE id=?', (client_id,)).fetchone()
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
                invite_email = request.form.get('email', '').strip().lower()
                if not business_name or not invite_name or not invite_email:
                    flash('Enter new customer name, contact name, and email before sending the invite.', 'error')
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
                invite_email = request.form.get('email', '').strip().lower()
                trial_days = default_trial_offer_days()
                if not business_name or not invite_name or not invite_email:
                    flash('Enter business name, contact name, and email before sending the trial invite.', 'error')
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
                           trial_offer_days, trial_started_at, trial_ends_at
                       ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
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
                try:
                    invite_payload = send_trial_invite_email(invite_email, invite_name, business_name, invite_link, trial_days=trial_days)
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
                    )
                    flash(f'Trial invite email failed: {str(e)[:180]}', 'error')
                return redirect(url_for('client_users'))
            if action == 'send_invite':
                client_id = request.form.get('client_id', type=int)
                token = generate_invite_token()
                expires_at = (datetime.utcnow() + timedelta(days=14)).strftime('%Y-%m-%d %H:%M:%S')
                conn.execute(
                    'INSERT INTO business_invites (client_id, invited_email, invited_name, token, status, created_by_user_id, expires_at, invite_error, invite_kind, trial_days) VALUES (?,?,?,?,?,?,?,?,?,?)',
                    (client_id, request.form.get('email', '').strip().lower(), request.form.get('full_name', '').strip(), token, 'pending', user['id'], expires_at, '', 'business_access', 0)
                )
                invite_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
                business = conn.execute('SELECT business_name FROM clients WHERE id=?', (client_id,)).fetchone()
                invite_link = build_invite_link(token)
                try:
                    invite_payload = send_invite_email(request.form.get('email', '').strip().lower(), request.form.get('full_name', '').strip(), (business['business_name'] if business else ''), invite_link)
                    conn.execute('UPDATE business_invites SET status="sent", invite_error="" WHERE id=?', (invite_id,))
                    conn.commit()
                    log_email_delivery(
                        client_id=client_id,
                        email_type=invite_payload['email_type'],
                        recipient_email=request.form.get('email', '').strip().lower(),
                        recipient_name=request.form.get('full_name', '').strip(),
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
                        recipient_email=request.form.get('email', '').strip().lower(),
                        recipient_name=request.form.get('full_name', '').strip(),
                        subject=f"Welcome to LedgerFlow - set up your business access for {(business['business_name'] if business else '')}",
                        status='failed',
                        error_message=str(e)[:500],
                        created_by_user_id=user['id'],
                        related_invite_id=invite_id,
                    )
                    flash(f'Invite email failed: {str(e)[:180]}', 'error')
                return redirect(url_for('client_users'))
            if action == 'resend_invite':
                invite_id = request.form.get('invite_id', type=int)
                inv = conn.execute('SELECT bi.*, c.business_name FROM business_invites bi JOIN clients c ON c.id=bi.client_id WHERE bi.id=?', (invite_id,)).fetchone()
                if not inv:
                    flash('Invite not found.', 'error')
                    return redirect(url_for('client_users'))
                invite_link = build_invite_link(inv['token'])
                try:
                    if normalize_invite_kind(inv['invite_kind']) == 'prospect_trial':
                        invite_payload = send_trial_invite_email(
                            inv['invited_email'],
                            inv['invited_name'],
                            inv['business_name'],
                            invite_link,
                            trial_days=int(inv['trial_days'] or 0),
                        )
                    else:
                        invite_payload = send_invite_email(inv['invited_email'], inv['invited_name'], inv['business_name'], invite_link)
                    conn.execute('UPDATE business_invites SET status="sent", invite_error="" WHERE id=?', (invite_id,))
                    conn.commit()
                    log_email_delivery(
                        client_id=inv['client_id'],
                        email_type=invite_payload['email_type'],
                        recipient_email=inv['invited_email'],
                        recipient_name=inv['invited_name'],
                        subject=invite_payload['subject'],
                        body_text=invite_payload['body_text'],
                        body_html=invite_payload['body_html'],
                        status='sent',
                        created_by_user_id=user['id'],
                        related_invite_id=invite_id,
                    )
                    flash('Invite re-sent. View it below in Recent Business Emails.', 'success')
                except Exception as e:
                    conn.execute('UPDATE business_invites SET status="failed", invite_error=? WHERE id=?', (str(e)[:500], invite_id))
                    conn.commit()
                    log_email_delivery(
                        client_id=inv['client_id'],
                        email_type='prospect_trial_invite' if normalize_invite_kind(inv['invite_kind']) == 'prospect_trial' else 'business_invite',
                        recipient_email=inv['invited_email'],
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
                       WHERE edl.client_id = c.id
                         AND edl.email_type IN ('business_invite', 'prospect_trial_invite')
                       ORDER BY edl.created_at DESC, edl.id DESC
                       LIMIT 1
                   ) AS last_invite_email_id,
                   (
                       SELECT edl.status
                       FROM email_delivery_log edl
                       WHERE edl.client_id = c.id
                         AND edl.email_type IN ('business_invite', 'prospect_trial_invite')
                       ORDER BY edl.created_at DESC, edl.id DESC
                       LIMIT 1
                   ) AS last_invite_email_status,
                   (
                       SELECT edl.email_type
                       FROM email_delivery_log edl
                       WHERE edl.client_id = c.id
                         AND edl.email_type IN ('business_invite', 'prospect_trial_invite')
                       ORDER BY edl.created_at DESC, edl.id DESC
                       LIMIT 1
                   ) AS last_invite_email_type,
                   (
                       SELECT edl.created_at
                       FROM email_delivery_log edl
                       WHERE edl.client_id = c.id
                         AND edl.email_type IN ('business_invite', 'prospect_trial_invite')
                       ORDER BY edl.created_at DESC, edl.id DESC
                       LIMIT 1
                   ) AS last_invite_email_sent_at
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
    prospect_clients = [dict(row) for row in prospect_clients]
    for row in prospect_clients:
        row['pipeline_stage'] = prospect_pipeline_stage(row)
    prospect_stage_counts = summarize_prospect_pipeline(prospect_clients)
    email_logs = recent_email_activity(visible_client_ids(user, include_non_active=True), limit=40)
    return render_template(
        'client_users.html',
        clients=active_clients,
        prospect_clients=prospect_clients,
        prospect_stage_counts=prospect_stage_counts,
        users=users,
        invites=invites,
        build_invite_link=build_invite_link,
        app_base_url=configured_base_url(),
        email_logs=email_logs,
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
    if not row:
        abort(404)
    if user['role'] != 'admin' and row['client_id'] is not None and row['client_id'] not in visible_client_ids(user, include_non_active=True):
        abort(403)
    preview_row = dict(row)
    preview_row['body_html'] = email_preview_html(row['body_html'] or '')
    return render_template('email_preview.html', email_row=preview_row)


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
                      c.subscription_plan_code, c.trial_offer_days, c.trial_started_at, c.trial_ends_at
               FROM business_invites bi
               JOIN clients c ON c.id=bi.client_id
               WHERE bi.token=?''',
            (token,)
        ).fetchone()
        if not invite:
            abort(404)
        expires_at = datetime.strptime(invite['expires_at'], '%Y-%m-%d %H:%M:%S')
        if invite['status'] != 'accepted' and datetime.utcnow() > expires_at:
            conn.execute('UPDATE business_invites SET status="expired" WHERE id=?', (invite['id'],))
            conn.commit()
            invite = conn.execute(
                '''SELECT bi.*, c.business_name, c.contact_name, c.email client_email, c.record_status, c.service_level,
                          c.subscription_plan_code, c.trial_offer_days, c.trial_started_at, c.trial_ends_at
                   FROM business_invites bi
                   JOIN clients c ON c.id=bi.client_id
                   WHERE bi.token=?''',
                (token,)
            ).fetchone()
        if request.method == 'POST' and invite['status'] in ('pending','sent','failed'):
            email = request.form.get('email', '').strip().lower()
            full_name = request.form.get('full_name', '').strip()
            password = request.form.get('password', '').strip()
            confirm_password = request.form.get('confirm_password', '').strip()
            existing = conn.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone()
            if not full_name:
                flash('Full name is required.', 'error')
            elif not email:
                flash('Email is required.', 'error')
            elif existing:
                flash('That email already has an account. Sign in instead, or use Forgot Password if needed.', 'error')
            elif len(password) < 8:
                flash('Password must be at least 8 characters.', 'error')
            elif password != confirm_password:
                flash('Passwords do not match.', 'error')
            else:
                conn.execute('INSERT INTO users (email, password_hash, full_name, role, client_id) VALUES (?,?,?,?,?)', (email, generate_password_hash(password), full_name, 'client', invite['client_id']))
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
                        flash('Trial claimed. Start in the Welcome Center, review the guided overview, and finish the quick setup when you are ready.', 'success')
                        return redirect(url_for('welcome_center'))
                    flash('Business login created. Complete setup to unlock your full LedgerFlow workspace.', 'success')
                    return redirect(url_for('business_onboarding'))
                if is_trial_claim:
                    flash('Trial claimed. Your LedgerFlow workspace is ready to explore.', 'success')
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
                    flash('Business login created. Welcome email sent. Sign in below.', 'success')
                elif smtp_email_ready():
                    flash(f'Business login created, but welcome email failed: {welcome_error}', 'error')
                else:
                    flash('Business login created. Sign in below.', 'success')
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
            'SELECT bi.*, c.business_name, c.record_status, c.onboarding_status FROM business_invites bi JOIN clients c ON c.id=bi.client_id WHERE bi.token=?',
            (token,)
        ).fetchone()
        if not invite:
            abort(404)
        expires_at = datetime.strptime(invite['expires_at'], '%Y-%m-%d %H:%M:%S')
        if invite['status'] != 'accepted' and datetime.utcnow() > expires_at:
            conn.execute('UPDATE business_invites SET status="expired" WHERE id=?', (invite['id'],))
            conn.commit()
            invite = conn.execute(
                'SELECT bi.*, c.business_name, c.record_status, c.onboarding_status FROM business_invites bi JOIN clients c ON c.id=bi.client_id WHERE bi.token=?',
                (token,)
            ).fetchone()
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
                flash('Your LedgerFlow workspace has been restored. Sign in to continue.', 'success')
                return redirect(url_for('main_portal'))
            flash('Workspace restored. Create your business login to continue.', 'success')
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
            )
            session['preferred_language'] = selected_language
            business_name = request.form.get('business_name', '').strip()
            business_structure = request.form.get('business_type', '').strip()
            business_category = normalize_business_category(request.form.get('business_category', ''))
            business_specialty = request.form.get('business_specialty', '').strip()[:120]
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
            if (not trial_payment_optional) or submitted_payment_method:
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
                       SET business_name=?, business_type=?, business_category=?, business_specialty=?, service_level=?, contact_name=?, phone=?, email=?, address=?, ein=?,
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
    with get_conn() as conn:
        if request.method == 'POST':
            action = request.form.get('action', 'add_invoice').strip()
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
            next_job = conn.execute('SELECT COALESCE(MAX(job_number),0)+1 n FROM invoices WHERE client_id=?', (client_id,)).fetchone()['n']
            conn.execute(
                'INSERT INTO invoices (client_id, job_number, client_name, client_address, paid_amount, invoice_date, notes, income_category, sales_tax_amount, sales_tax_paid) VALUES (?,?,?,?,?,?,?,?,?,?)',
                (
                    client_id,
                    next_job,
                    request.form.get('client_name', '').strip(),
                    request.form.get('client_address', '').strip(),
                    request.form.get('paid_amount', type=float) or 0,
                    request.form.get('invoice_date', '').strip(),
                    request.form.get('notes', '').strip(),
                    request.form.get('income_category', 'service_income').strip() or 'service_income',
                    request.form.get('sales_tax_amount', type=float) or 0,
                    1 if request.form.get('sales_tax_paid') else 0,
                )
            )
            conn.commit()
            flash('Income record saved.', 'success')
            return redirect(url_for('invoices', client_id=client_id))
        rows = conn.execute('SELECT * FROM invoices WHERE client_id=? ORDER BY job_number DESC, id DESC', (client_id,)).fetchall()
        invoice_mileage_rows = conn.execute('''
            SELECT im.*, i.job_number, i.client_name
            FROM invoice_mileage_entries im
            LEFT JOIN invoices i ON i.id = im.invoice_id
            WHERE im.client_id=?
            ORDER BY im.trip_date DESC, im.id DESC
        ''', (client_id,)).fetchall()
        client = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
    return render_template(
        'invoices.html',
        invoices=rows,
        invoice_mileage_entries=invoice_mileage_rows,
        client=client,
        client_id=client_id,
        home_address=DEFAULT_HOME_ADDRESS,
        income_category_options=income_category_options(),
        income_category_labels=income_category_label_map(),
    )


@app.route('/invoice/<int:invoice_id>')
@login_required
def invoice_print(invoice_id):
    user = current_user()
    with get_conn() as conn:
        row = conn.execute('SELECT i.*, c.business_name FROM invoices i JOIN clients c ON c.id=i.client_id WHERE i.id=?', (invoice_id,)).fetchone()
    if not row or not allowed_client(user, row['client_id']):
        abort(403)
    return render_template('invoice_print.html', invoice=row)


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
        invoices = conn.execute('SELECT * FROM invoices WHERE client_id=? ORDER BY job_number DESC, id DESC', (client_id,)).fetchall()

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
            query = 'SELECT * FROM invoices WHERE client_id=?'
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
    with get_conn() as conn:
        client = conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
        workers = conn.execute('SELECT id, name, status FROM workers WHERE client_id=? ORDER BY CASE WHEN status="active" THEN 0 ELSE 1 END, name', (client_id,)).fetchall()
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
                        client_id, job_name, job_address, scope_of_work, schedule_date,
                        start_time, end_time, estimated_duration, assigned_worker_ids,
                        assigned_worker_names, notes, created_by_user_id
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (
                        client_id,
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
        entries=entries,
        upcoming_entries=upcoming_entries,
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
