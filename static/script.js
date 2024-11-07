const cart = [];
let total = 0;


function addToCart(id, name, price) {
    const customizationInput = document.getElementById(`customization-${id}`);
    const customization = customizationInput ? customizationInput.value : '';

    const existingItem = cart.find(item => item.id === id && item.customization === customization);

    if (existingItem) {
        existingItem.quantity += 1;
        existingItem.totalPrice += price;
    } else {
        cart.push({ id, name, price, quantity: 1, totalPrice: price, customization });
    }

    if (customization) {
        total += price + 5;
    } else {
        total += price;
    }
    
    updateCart();

    const cartToggleButton = document.getElementById("cart-toggle-btn");
    cartToggleButton.classList.add("shake");
    setTimeout(() => cartToggleButton.classList.remove("shake"), 500);
}

function removeFromCart(id, customization = '') {
    // Znajdź indeks pozycji w koszyku, biorąc pod uwagę również personalizację
    const itemIndex = cart.findIndex(item => item.id === id && item.customization === customization);
    
    if (itemIndex !== -1) {
        total -= cart[itemIndex].totalPrice;
        cart.splice(itemIndex, 1);
    }
    updateCart();
}

function updateCart() {
    const cartItemsList = document.getElementById("cart-items");
    cartItemsList.innerHTML = "";

    cart.forEach(item => {
        const listItem = document.createElement("li");
        listItem.innerHTML = `
            ${item.name} - Ilość: ${item.quantity} x ${item.price.toFixed(2)} PLN = ${item.totalPrice.toFixed(2)} PLN
            ${item.customization ? `<br><em style="color:#808080;">Personalizacja: ${item.customization} (+5 PLN)</em>` : ""}
            <button onclick="removeFromCart(${item.id}, '${item.customization}')" class="remove-btn">Usuń</button>
        `;
        cartItemsList.appendChild(listItem);
    });

    // Aktualizacja łącznej ceny na przycisku koszyka
    document.getElementById("cart-toggle-btn").innerHTML = `Pokaż Koszyk<br><span>${total.toFixed(2)} PLN 🛒</span>`;

    document.getElementById("cart-total").innerText = total.toFixed(2);
}

function submitOrder() {
    if (cart.length === 0) {
        alert("Koszyk jest pusty! Dodaj produkty przed złożeniem zamówienia.");
        return;
    }

    const urlPath = window.location.pathname;
    const tableId = urlPath.split("/").pop();

    const confirmation = window.confirm("Czy na pewno chcesz złożyć zamówienie? Wybrane dania zostaną przekazane do realizacji.");
    
    if (confirmation) {
        fetch('/order', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ table_id: parseInt(tableId), items: cart })
        })
        .then(response => response.json())
        .then(data => {
            window.location.href = `/order_status/${data.order_id}`;
        });
    }
}

function toggleCart() {
    const cart = document.getElementById("cart");
    cart.classList.toggle("show");

    const toggleBtn = document.getElementById("cart-toggle-btn");
    if (cart.classList.contains("show")) {
        toggleBtn.innerHTML = `Ukryj Koszyk<br><span>${total.toFixed(2)} PLN 🛒</span>`;
    } else {
        toggleBtn.innerHTML = `Pokaż Koszyk<br><span>${total.toFixed(2)} PLN 🛒</span>`;
    }
}
