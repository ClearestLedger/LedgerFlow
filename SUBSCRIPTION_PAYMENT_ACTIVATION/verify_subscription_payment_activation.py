import hashlib
import hmac
import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='ledgerflow_stripe_verify_')
os.environ['APP_BASE_URL'] = 'https://ledgerflow-vprm.onrender.com'
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from werkzeug.security import generate_password_hash

import _live_sync_tmp.app as ledger
from _live_sync_tmp.app import (
    app,
    get_conn,
    TERMS_VERSION,
    PRIVACY_VERSION,
    DISCLAIMER_VERSION,
)


def seed_business():
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users (email,password_hash,full_name,role,preferred_language) VALUES (?,?,?,?,?)",
            ('admin@example.com', generate_password_hash('pass'), 'Admin', 'admin', 'en'),
        )
        admin_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        conn.execute(
            """INSERT INTO clients
               (business_name, service_level, subscription_plan_code, subscription_amount, subscription_status, contact_name, email)
               VALUES (?,?,?,?,?,?,?)""",
            ('RDS HOME SOLUTIONS', 'self_service', 'essential-client-monthly', 59, 'inactive', 'Danielle', 'test@example.com'),
        )
        client_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        conn.execute(
            """INSERT INTO legal_acceptances
               (user_id, client_id, terms_version, privacy_version, disclaimer_version, acceptance_method)
               VALUES (?,?,?,?,?,?)""",
            (admin_id, client_id, TERMS_VERSION, PRIVACY_VERSION, DISCLAIMER_VERSION, 'verify'),
        )
        conn.commit()
    return admin_id, client_id


def sign_stripe_payload(payload: bytes, secret: str) -> str:
    timestamp = str(int(time.time()))
    signature = hmac.new(secret.encode('utf-8'), f'{timestamp}.'.encode('utf-8') + payload, hashlib.sha256).hexdigest()
    return f't={timestamp},v1={signature}'


def main():
    admin_id, client_id = seed_business()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session['user_id'] = admin_id
            session['payment_csrf_token'] = 'verify-token'
            session['accepted_terms_version'] = TERMS_VERSION
            session['accepted_privacy_version'] = PRIVACY_VERSION
            session['accepted_disclaimer_version'] = DISCLAIMER_VERSION

        page = client.get(f'/business-payments?client_id={client_id}')
        assert page.status_code == 200, page.status_code
        assert b'Secure Subscription Checkout' in page.data
        assert b'Stripe checkout not connected yet' in page.data

        missing_config = client.post(
            '/business-payments/stripe-checkout',
            data={'client_id': client_id, 'csrf_token': 'verify-token'},
            follow_redirects=False,
        )
        assert missing_config.status_code == 302

        os.environ['STRIPE_SECRET_KEY'] = 'sk_test_dummy'
        os.environ['STRIPE_PRICE_SELF_SERVICE'] = 'price_test_essential'
        captured = {}

        def fake_stripe_post(path, data):
            captured['path'] = path
            captured['data'] = dict(data)
            return {'id': 'cs_test_verify', 'url': 'https://checkout.stripe.test/session'}

        ledger.stripe_api_post = fake_stripe_post
        checkout = client.post(
            '/business-payments/stripe-checkout',
            data={'client_id': client_id, 'csrf_token': 'verify-token'},
            follow_redirects=False,
        )
        assert checkout.status_code == 302
        assert checkout.headers['Location'] == 'https://checkout.stripe.test/session'
        assert captured['path'] == '/checkout/sessions'
        assert captured['data']['line_items[0][price]'] == 'price_test_essential'
        assert captured['data']['metadata[client_id]'] == str(client_id)

        os.environ['STRIPE_WEBHOOK_SECRET'] = 'whsec_verify_secret'
        event = {
            'id': 'evt_verify_checkout',
            'type': 'checkout.session.completed',
            'data': {
                'object': {
                    'id': 'cs_test_verify',
                    'object': 'checkout.session',
                    'customer': 'cus_test_verify',
                    'subscription': 'sub_test_verify',
                    'metadata': {'client_id': str(client_id)},
                }
            },
        }
        payload = json.dumps(event, separators=(',', ':')).encode('utf-8')
        webhook = client.post(
            '/stripe/webhook',
            data=payload,
            headers={'Stripe-Signature': sign_stripe_payload(payload, 'whsec_verify_secret')},
            content_type='application/json',
        )
        assert webhook.status_code == 200, webhook.get_data(as_text=True)

    with get_conn() as conn:
        row = conn.execute(
            '''SELECT subscription_status, stripe_customer_id, stripe_subscription_id, stripe_checkout_session_id
               FROM clients WHERE id=?''',
            (client_id,),
        ).fetchone()
        assert row['subscription_status'] == 'active'
        assert row['stripe_customer_id'] == 'cus_test_verify'
        assert row['stripe_subscription_id'] == 'sub_test_verify'
        assert row['stripe_checkout_session_id'] == 'cs_test_verify'

    print('SUBSCRIPTION_PAYMENT_ACTIVATION_VERIFY=PASS')


if __name__ == '__main__':
    main()
