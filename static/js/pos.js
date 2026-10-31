/**
 * Enterprise POS client. The browser only selects real catalog records and
 * presents a live estimate; Billing.create_bill remains the server source
 * of truth for stock, tax, discounts and totals.
 */
let cart = [];
let checkoutPreview = null;
function csrfToken() {
    const meta=document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
}
function money(v) {
    return `₹${Number(v||0).toLocaleString('en-IN',{minimumFractionDigits:2,maximumFractionDigits:2})}`;
}
function findProduct(id) {
    return (window.PRODUCT_CATALOG||[]).find(p=>Number(p.id)===Number(id));
}
function findProductByText(text) {
    const q=String(text||'').trim().toLowerCase();
    if(!q)return null;
    const list=window.PRODUCT_CATALOG||[];
    return list.find(p=>String(p.name||'').toLowerCase()===q || String(p.sku||'').toLowerCase()===q || String(p.barcode||'').toLowerCase()===q)
    || list.find(p=>String(p.name||'').toLowerCase().includes(q) || String(p.sku||'').toLowerCase().includes(q) || String(p.barcode||'').toLowerCase().includes(q));
}
function addToCart(id, name, price, stock, quantity=1) {
    id=Number(id);
    quantity=Math.max(1,parseInt(quantity,10)||1);
    const existing=cart.find(c=>Number(c.product_id)===id);
    if(existing) {
        if(existing.quantity+quantity>Number(stock)) {
            alert(`Not enough stock. Available: ${stock}`);
            return false;
        }
        existing.quantity+=quantity;
    }else {
        if(Number(stock)<=0) {
            alert('This product is out of stock.');
            return false;
        }
        if(quantity>Number(stock)) {
            alert(`Only ${stock} unit(s) are available.`);
            return false;
        }
        cart.push( {
            product_id:id,name:String(name),price:Number(price),quantity,stock:Number(stock)
        });
    }
    renderCart();
    refreshCheckoutPreview().catch(()=> {
    });
    return true;
}
function updateQty(id,qty) {
    const item=cart.find(c=>Number(c.product_id)===Number(id));
    if(!item)return;
    qty=Math.max(1,parseInt(qty,10)||1);
    if(qty>item.stock) {
        alert(`Not enough stock. Available: ${item.stock}`);
        qty=item.stock;
    }
    item.quantity=qty;
    renderCart();
    refreshCheckoutPreview().catch(()=> {
    });
}
function removeFromCart(id) {
    cart=cart.filter(c=>Number(c.product_id)!==Number(id));
    renderCart();
    refreshCheckoutPreview().catch(()=> {
    });
}
function renderCart() {
    const container=document.getElementById('cart-items');
    if(!container)return;
    container.innerHTML='';
    if(!cart.length) {
        container.innerHTML='<div class="cart-empty">No items added yet. Scan or manually select a product.</div>';
    }
    cart.forEach(item=> {
        const line=Number(item.price)*Number(item.quantity);
        const row=document.createElement('div');
        row.className='cart-row';
        const prod=document.createElement('div');
        prod.className='cart-product';
        const strong=document.createElement('strong');
        strong.textContent=item.name;
        const small=document.createElement('small');
        const p=findProduct(item.product_id);
        small.textContent=p?.sku||p?.barcode||'Product';
        prod.append(strong,small);
        const price=document.createElement('span');
        price.className='cart-price';
        price.textContent=money(item.price);
        const qty=document.createElement('input');
        qty.className='qty-control';
        qty.type='number';
        qty.min='1';
        qty.max=String(item.stock);
        qty.value=String(item.quantity);
        qty.addEventListener('change',()=>updateQty(item.product_id,qty.value));
        const total=document.createElement('span');
        total.className='cart-total';
        total.textContent=money(line);
        const remove=document.createElement('button');
        remove.type='button';
        remove.className='cart-remove';
        remove.textContent='×';
        remove.title='Remove item';
        remove.addEventListener('click',()=>removeFromCart(item.product_id));
        row.append(prod,price,qty,total,remove);
        container.appendChild(row);
    });
    const count=cart.reduce((n,i)=>n+i.quantity,0);
    const countEl=document.getElementById('cart-count');
    if(countEl)countEl.textContent=`${count} item${count===1?'':'s'}`;
    if(!cart.length)updateTotals( {
        subtotal:0,discount:0,cgst:0,sgst:0,igst:0,total:0
    });
    updateChange();
}
function updateTotals(t) {
    const fields= {
        subtotal:'t-subtotal',discount:'t-discount',cgst:'t-cgst',sgst:'t-sgst',igst:'t-igst',total:'t-total'
    };
    Object.entries(fields).forEach(([key,id])=> {
        const el=document.getElementById(id);
        if(el)el.textContent=money(t[key]||0);
    });
    updateChange();
}
function updateChange() {
    const total=Number(checkoutPreview?.total||0);
    const method=document.getElementById('payment-method')?.value;
    const received=Number(document.getElementById('amount-received')?.value||0);
    const el=document.getElementById('change-due');
    if(!el)return;
    const change=method==='cash' ? Math.max(0,received-total) : 0;
    el.textContent=money(change);
}
function refreshCheckoutPreview() {
    if(!cart.length) {
        checkoutPreview=null;
        updateTotals( {
        });
        return Promise.resolve(null);
    }
    const payload= {
        items:cart.map(c=>( {
            product_id:c.product_id,quantity:c.quantity
        })),customer_state:document.getElementById('customer-state')?.value||null,coupon_code:document.getElementById('coupon-code')?.value.trim()||null
    };
    return fetch('/admin/billing/preview', {
        method:'POST',headers: {
            'Content-Type':'application/json','X-CSRFToken':csrfToken()
        },body:JSON.stringify(payload)
    })
    .then(r=>r.json()).then(data=> {
        if(!data.ok)throw new Error(data.message||'Unable to calculate bill.');
        checkoutPreview=data;
        updateTotals(data);
        return data;
    });
}
function buildPaymentMethods(total) {
    const method=document.getElementById('payment-method').value;
    if(method!=='split')return [ {
        method,amount:Number(total)
    }];
    const parts=[];
    ['cash','upi','card','wallet'].forEach(m=> {
        const v=Number(document.getElementById(`split-${m}`).value||0);
        if(v>0)parts.push( {
            method:m,amount:v
        });
    });
    return parts;
}
function checkout() {
    if(!cart.length) {
        alert('Cart is empty.');
        return;
    }
    refreshCheckoutPreview().then(t=> {
        const total=Number(t.total||0),method=document.getElementById('payment-method').value;
        const received=Number(document.getElementById('amount-received').value||0);
        if(method==='cash' && received<total) {
            alert(`Amount received must be at least ${money(total)}.`);
            return;
        }
        const paymentMethods=buildPaymentMethods(total);
        const paid=paymentMethods.reduce((sum,p)=>sum+Number(p.amount||0),0);
        if(Math.abs(paid-total)>0.009) {
            alert(`Payment amount must equal ${money(total)}.`);
            return;
        }
        const payload= {
            items:cart.map(c=>( {
                product_id:c.product_id,quantity:c.quantity
            })),customer_id:document.getElementById('customer-select').value||null,customer_state:document.getElementById('customer-state').value||null,coupon_code:document.getElementById('coupon-code').value.trim()||null,payment_methods:paymentMethods,hold_id:window.RESUME_ID||null
        };
        return fetch('/admin/billing/checkout', {
            method:'POST',headers: {
                'Content-Type':'application/json','X-CSRFToken':csrfToken()
            },body:JSON.stringify(payload)
        }).then(r=>r.json()).then(data=> {
            if(data.ok)window.location.href=`/admin/billing/invoice/${data.sale_id}`;
            else alert(data.message||'Unable to complete sale.');
        });
    }).catch(err=>alert(err.message||'Unable to calculate checkout total.'));
}
function holdBill() {
    if(!cart.length) {
        alert('Cart is empty.');
        return;
    }
    fetch('/admin/billing/hold', {
        method:'POST',headers: {
            'Content-Type':'application/json','X-CSRFToken':csrfToken()
        },body:JSON.stringify( {
            items:cart,customer_id:document.getElementById('customer-select').value||null
        })
    })
    .then(r=>r.json()).then(data=> {
        if(data.ok) {
            alert('Bill held successfully.');
            cart=[];
            checkoutPreview=null;
            renderCart();
        }else alert(data.message||'Unable to hold bill.');
    });
}
function selectCatalogProduct(product,quantity=1) {
    if(product)addToCart(product.id,product.name,product.price,product.stock,quantity);
}
function manualSelect(product) {
    const price=document.getElementById('manual-price'),selected=document.getElementById('manual-selected');
    if(!product) {
        if(price)price.value='';
        if(selected)selected.textContent='No matching product found in the live database catalog.';
        return;
    }
    if(price)price.value=Number(product.price).toFixed(2);
    if(selected)selected.textContent=`Selected: ${product.name} · ${product.sku||product.barcode||'No SKU/barcode'} · Available stock: ${product.stock}`;
}
function setup() {
    const tabs=document.querySelectorAll('[data-pos-tab]');
    tabs.forEach(tab=>tab.addEventListener('click',()=> {
        tabs.forEach(t=>t.classList.toggle('active',t===tab));
        document.querySelectorAll('.pos-tab-panel').forEach(p=>p.hidden=p.id!==`pos-tab-${tab.dataset.posTab}`);
        document.querySelectorAll('.pos-tab-panel').forEach(p=>p.classList.toggle('active',!p.hidden));
    }));
    document.querySelectorAll('.product-tile').forEach(card=>card.addEventListener('click',()=>selectCatalogProduct( {
        id:Number(card.dataset.productId),name:card.dataset.productName,price:Number(card.dataset.price),stock:Number(card.dataset.stock)
    })));
    const scan=document.getElementById('barcode-input');
    scan?.addEventListener('keydown',e=> {
        if(e.key!=='Enter')return;
        e.preventDefault();
        const product=findProductByText(scan.value);
        if(product)selectCatalogProduct(product);
        else alert('No matching product found. Enter a valid product name, SKU or barcode.');
        scan.value='';
    });
    document.getElementById('scan-focus')?.addEventListener('click',()=>scan?.focus());
    const manualName=document.getElementById('manual-product-name'),manualCode=document.getElementById('manual-code');
    const updateManual=()=> {
        const p=findProductByText(manualCode?.value)||findProductByText(manualName?.value);
        manualSelect(p);
    };
    manualName?.addEventListener('input',updateManual);
    manualName?.addEventListener('change',updateManual);
    manualCode?.addEventListener('input',updateManual);
    manualCode?.addEventListener('change',updateManual);
    document.getElementById('manual-add')?.addEventListener('click',()=> {
        const p=findProductByText(manualCode?.value)||findProductByText(manualName?.value);
        const qty=Number(document.getElementById('manual-qty')?.value||1);
        if(!p) {
            alert('Select a valid product from the database catalog.');
            return;
        }
        if(addToCart(p.id,p.name,p.price,p.stock,qty)) {
            manualName.value='';
            manualCode.value='';
            document.getElementById('manual-price').value='';
            document.getElementById('manual-selected').textContent='Product added to cart.';
            document.getElementById('manual-qty').value='1';
        }
    });
    document.getElementById('payment-method')?.addEventListener('change',e=> {
        const split=document.getElementById('split-payments');
        if(split)split.hidden=e.target.value!=='split';
        const amount=document.getElementById('amount-received');
        if(amount)amount.value=e.target.value==='cash'?'':(checkoutPreview?.total||'');
        updateChange();
    });
    document.getElementById('amount-received')?.addEventListener('input',updateChange);
    ['customer-state','coupon-code'].forEach(id=>document.getElementById(id)?.addEventListener('change',()=>refreshCheckoutPreview().catch(err=>alert(err.message))));
    document.getElementById('coupon-apply')?.addEventListener('click',()=>refreshCheckoutPreview().catch(err=>alert(err.message)));
    document.querySelectorAll('[data-pos-action]').forEach(b=>b.addEventListener('click',()=>b.dataset.posAction==='hold'?holdBill():checkout()));
    if(window.RESUME_CART) {
        try {
            const parsed=Array.isArray(window.RESUME_CART)?window.RESUME_CART:JSON.parse(window.RESUME_CART);
            cart=parsed.map(i=> {
                const p=findProduct(i.product_id);
                return {
                    product_id:i.product_id,name:i.name||p?.name||'Item',price:Number(i.price||p?.price||0),quantity:Number(i.quantity||1),stock:Number(p?.stock||i.quantity||1)
                };
            });
            renderCart();
            refreshCheckoutPreview().catch(()=> {
            });
        } catch(e) {
        }
    }
}
document.addEventListener('DOMContentLoaded',setup);
