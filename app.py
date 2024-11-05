from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event, func
from dotenv import load_dotenv
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
import os
import pytz

load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL", "sqlite:///database.db")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.getenv("SECRET_KEY")
db = SQLAlchemy(app)
app.config['DEBUG'] = False
app.config['UPLOAD_FOLDER'] = 'static/images'  # Ścieżka do przechowywania zdjęć

# Modele bazy danych
class Table(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    qr_code = db.Column(db.String(100), unique=True)

class MenuItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    description = db.Column(db.String(200))
    price = db.Column(db.Float)
    customizable = db.Column(db.Boolean, default=False)
    category = db.Column(db.String(50))
    image_filename = db.Column(db.String(100))
    display_date = db.Column(db.Date, nullable=True)


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    table_id = db.Column(db.Integer, db.ForeignKey('table.id'))
    status = db.Column(db.String(50), default='Pending')
    total_price = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    order_items = db.relationship('OrderItem', backref='order', lazy=True)
    call_waiter = db.Column(db.Boolean, default=False)
    last_call_time = db.Column(db.DateTime, nullable=True)
    request_bill = db.Column(db.Boolean, default=False)  # Nowe pole do prośby o rachunek
    bill_payment_method = db.Column(db.String(50), nullable=True)
    order_number = db.Column(db.Integer)

    @staticmethod
    def generate_order_number():
        # Definiujemy strefę czasową
        timezone = pytz.timezone('Europe/Warsaw')
        today = datetime.now(timezone).date()

        # Znalezienie maksymalnego numeru zamówienia dla bieżącego dnia
        last_order_number = db.session.query(func.max(Order.order_number)).filter(
            func.date(Order.created_at) == today
        ).scalar()

        # Jeśli brak zamówień na dzisiejszy dzień, zaczynamy od 1; w przeciwnym razie zwiększamy numer
        return 1 if last_order_number is None else last_order_number + 1

# Event do ustawienia order_number dla nowego zamówienia
@event.listens_for(Order, 'before_insert')
def set_order_number(mapper, connection, target):
    target.order_number = Order.generate_order_number()


class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    menu_item_id = db.Column(db.Integer, db.ForeignKey('menu_item.id'))
    quantity = db.Column(db.Integer)
    customization = db.Column(db.String(200))
    menu_item = db.relationship('MenuItem')

@app.route("/")
def index():
    return "Hello, Vercel!"

# Widok głównego menu dla klientów
@app.route('/menu/<int:table_id>')
def menu(table_id):
    # Aktualna godzina w strefie czasowej UTC+1
    timezone = pytz.timezone('Europe/Warsaw')
    current_time = datetime.now(timezone)

    categories = {
        "Lunch Dnia": MenuItem.query.filter_by(category="Lunch Dnia").all(),
        "Deser Dnia": MenuItem.query.filter_by(category="Deser Dnia").all(),
        "Śniadania": MenuItem.query.filter_by(category="Śniadania").all(),
        "Bowle": MenuItem.query.filter_by(category="Bowle").all(),
        "Zupy": MenuItem.query.filter_by(category="Zupy").all(),
        "Sałatki": MenuItem.query.filter_by(category="Sałatki").all(),
        "Dania gorące": MenuItem.query.filter_by(category="Dania gorące").all(),
        "Przystawki": MenuItem.query.filter_by(category="Przystawki").all(),
        "Desery": MenuItem.query.filter_by(category="Desery").all(),
        "Napoje": MenuItem.query.filter_by(category="Napoje").all()
    }
    return render_template('menu.html', categories=categories, table_id=table_id, current_time=current_time)



@app.route('/check_new_orders', methods=['GET'])
def check_new_orders():
    try:
        timezone = pytz.timezone('Europe/Warsaw')
        new_orders = Order.query.filter_by(status="Pending").all()
        
        orders = [
            {
                "order_id": order.id,
                "order_number": order.order_number,
                "table_id": order.table_id,
                "status": order.status,
                "total_price": order.total_price,
                "order_time": order.created_at.replace(tzinfo=pytz.utc).astimezone(timezone).strftime("%H:%M"),
                "items": [
                    {
                        "name": item.menu_item.name,
                        "quantity": item.quantity,
                        "price": item.menu_item.price,
                        "customization": item.customization
                    }
                    for item in order.order_items
                ]
            }
            for order in new_orders
        ]
        
        print(f"Przetworzone zamówienia: {orders}")  # Dodatkowe logowanie do debugowania
        return jsonify(orders)

    except Exception as e:
        print(f"Błąd podczas pobierania zamówień: {e}")
        return jsonify({"error": "Wystąpił błąd podczas pobierania zamówień"}), 500



@app.route('/request_bill/<int:order_id>', methods=['POST'])
def request_bill(order_id):
    data = request.json
    payment_method = data.get('payment_method')
    
    order = Order.query.get_or_404(order_id)
    order.request_bill = True
    order.bill_payment_method = payment_method
    db.session.commit()
    
    return jsonify({"status": "success", "message": "Poproszono o rachunek"})

@app.route('/call_waiter/<int:order_id>', methods=['POST'])
def call_waiter(order_id):
    order = Order.query.get_or_404(order_id)
    
    # Sprawdzenie, czy minęły 3 minuty od ostatniego wezwania
    if order.last_call_time and datetime.utcnow() - order.last_call_time < timedelta(minutes=3):
        return jsonify({"status": "error", "message": "Musisz poczekać zanim ponownie wezwiesz kelnera"}), 403

    # Aktualizacja wezwania kelnera
    order.call_waiter = True
    order.last_call_time = datetime.utcnow()  # Ustawienie czasu ostatniego wezwania
    db.session.commit()
    return jsonify({"status": "success"})

@app.route('/check_waiter_calls', methods=['GET'])
def check_waiter_calls():
    # Pobieramy zamówienia z aktywnym wezwaniem kelnera lub prośbą o rachunek
    orders_with_calls = Order.query.filter((Order.call_waiter == True) | (Order.request_bill == True)).all()
    
    # Definiujemy strefę czasową UTC+1
    timezone = pytz.timezone('Europe/Warsaw')
    
    # Przygotowanie listy powiadomień dla kelnera
    calls = []
    for order in orders_with_calls:
        # Formatowanie informacji o wezwaniu lub prośbie o rachunek
        call_data = {
            "order_id": order.id,
            "order_number": order.order_number,
            "table_id": order.table_id,
            "call_type": "Wezwanie kelnera" if order.call_waiter else "Prośba o rachunek",
            "call_time": order.last_call_time.replace(tzinfo=pytz.utc).astimezone(timezone).strftime("%H:%M:%S") 
                if order.call_waiter and order.last_call_time else None,
            "payment_method": order.bill_payment_method if order.request_bill else None
        }
        calls.append(call_data)
    
    return jsonify(calls)


@app.route('/dismiss_call/<int:order_id>', methods=['POST'])
def dismiss_call(order_id):
    order = Order.query.get_or_404(order_id)
    order.call_waiter = False
    db.session.commit()
    return jsonify({"status": "success", "message": "Powiadomienie o wezwaniu kelnera zamknięte."})

@app.route('/dismiss_bill/<int:order_id>', methods=['POST'])
def dismiss_bill(order_id):
    order = Order.query.get_or_404(order_id)
    order.request_bill = False
    order.bill_payment_method = None  # Resetujemy metodę płatności
    db.session.commit()
    return jsonify({"status": "success", "message": "Powiadomienie o prośbie o rachunek zamknięte."})

# Obsługa zamówienia
@app.route('/order', methods=['POST'])
def place_order():
    data = request.json
    table_id = data.get('table_id')
    items = data.get('items')
    
    total_price = 0
    
    # Oblicz całkowitą cenę zamówienia, dodając opłatę 5 zł za personalizację, jeśli jest obecna
    for item in items:
        item_price = item['totalPrice']
        if item.get('customization'):  # Jeśli istnieje personalizacja
            item_price += 5  # Dodanie opłaty 5 zł za personalizację
        total_price += item_price * item['quantity']  # Uwzględnienie ilości przy sumowaniu

    # Tworzymy nowe zamówienie z `table_id` i łączną ceną
    new_order = Order(table_id=table_id, total_price=total_price)
    db.session.add(new_order)
    db.session.commit()
    
    # Dodajemy wszystkie pozycje zamówienia do tabeli OrderItem
    for item in items:
        order_item = OrderItem(
            order_id=new_order.id,
            menu_item_id=item['id'],
            quantity=item['quantity'],
            customization=item.get('customization', '')
        )
        db.session.add(order_item)
    db.session.commit()
    
    return jsonify({'order_id': new_order.id, 'status': 'Order placed'})



# Widok statusu zamówienia
@app.route('/order_status/<int:order_id>')
def order_status(order_id):
    order = Order.query.get_or_404(order_id)
    elapsed_time = datetime.utcnow() - order.created_at
    remaining_time = timedelta(minutes=15) - elapsed_time
    remaining_seconds = int(remaining_time.total_seconds())  # Przekształcenie na liczbę sekund
    return render_template('order_status.html', order=order, remaining_seconds=remaining_seconds)




# Widok kelnera
@app.route('/waiter_view')
def waiter_view():
    # Pobieranie tylko zamówień oczekujących
    active_orders = Order.query.filter(Order.status != 'Completed').all()
    
    # Strefa czasowa UTC+1 (Europe/Warsaw)
    timezone = pytz.timezone('Europe/Warsaw')
    
    # Konwersja pola `created_at` na UTC+1 dla każdego zamówienia
    for order in active_orders:
        if order.created_at:
            order.created_at = order.created_at.replace(tzinfo=pytz.utc).astimezone(timezone)
    
    return render_template('waiter_view.html', orders=active_orders)

@app.route('/order_history')
def order_history():
    # Pobieranie tylko zrealizowanych zamówień
    completed_orders = Order.query.filter_by(status='Completed').all()
    return render_template('order_history.html', orders=completed_orders)


@app.route('/update_order_status/<int:order_id>', methods=['POST'])
def update_order_status(order_id):
    order = Order.query.get_or_404(order_id)
    order.status = 'Completed'
    db.session.commit()
    flash("Status zamówienia został zaktualizowany.")
    return redirect(url_for('waiter_view'))


# Panel administratora
@app.route('/admin')
def admin_panel():
    menu_items = MenuItem.query.all()
    return render_template('admin_panel.html', menu_items=menu_items)


# Dodawanie nowego dania
@app.route('/add_menu_item', methods=['POST'])
def add_menu_item():
    name = request.form['name']
    description = request.form.get('description', '')  # Pusty ciąg, jeśli brak opisu
    price = float(request.form['price'])
    category = request.form['category']
    customizable = 'customizable' in request.form
    display_date = request.form.get('display_date')

    # Ustawiamy `display_date` na obiekt daty lub `None`
    display_date = datetime.strptime(display_date, '%Y-%m-%d').date() if display_date else None

    # Obsługa zdjęcia
    image = request.files['image']
    if image and image.filename != '':
        filename = secure_filename(image.filename)
        image.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        image_filename = filename
    else:
        image_filename = None  # Brak zdjęcia

    # Tworzenie nowego dania
    new_item = MenuItem(
        name=name,
        description=description,
        price=price,
        customizable=customizable,
        category=category,
        image_filename=image_filename,
        display_date=display_date
    )
    
    db.session.add(new_item)
    db.session.commit()
    flash('Dodano nowe danie do menu.')
    return redirect(url_for('admin_panel'))


@app.route('/healthz')
def health_check():
    return "OK", 200

# Edycja pozycji menu
@app.route('/edit_menu_item/<int:item_id>', methods=['POST'])
def edit_menu_item(item_id):
    item = MenuItem.query.get_or_404(item_id)

    item.name = request.form['name']
    item.description = request.form['description']
    item.price = float(request.form['price'])
    item.category = request.form['category']
    item.customizable = 'customizable' in request.form

    # Obsługa zmiany zdjęcia
    if 'image' in request.files:
        image = request.files['image']
        if image:
            # Usunięcie starego pliku zdjęcia, jeśli istnieje
            if item.image_filename:
                old_image_path = os.path.join(app.config['UPLOAD_FOLDER'], item.image_filename)
                if os.path.exists(old_image_path):
                    os.remove(old_image_path)
            # Zapis nowego zdjęcia
            filename = secure_filename(image.filename)
            image.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            item.image_filename = filename

    db.session.commit()
    flash('Danie zostało zaktualizowane.')
    return redirect(url_for('admin_panel'))


# Usuwanie pozycji menu
@app.route('/delete_menu_item/<int:item_id>', methods=['POST'])
def delete_menu_item(item_id):
    item = MenuItem.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    flash('Usunięto pozycję z menu.')
    return redirect(url_for('admin_panel'))

# Inicjalizacja bazy danych i uruchomienie aplikacji
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))  # Użyj zmiennej PORT, jeśli jest ustawiona
    app.run(host="0.0.0.0", port=port)