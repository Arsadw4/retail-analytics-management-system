/**
 * scan.js
 * Drives the barcode/QR scan page. Uses html5-qrcode (camera-based
 * decoding, loaded via CDN in scan.html) when a camera is available,
 * and always supports typing/scanning a code into the manual input
 * (many handheld barcode scanners act as keyboard-input devices, so
 * this covers that hardware too without any extra integration work).
 */
document.addEventListener("DOMContentLoaded", function () {
    const resultBox = document.getElementById("result");
    const notFoundBox = document.getElementById("not-found");
    const manualInput = document.getElementById("manual-code");
    function lookupCode(code) {
        if (!code) return;
        fetch(`/api/products/lookup-barcode/${encodeURIComponent(code)}`)
        .then((resp) => resp.json().then((data) => ( {
            status: resp.status, data
        })))
        .then(( {
            status, data
        }) => {
            if (status === 200 && data.found) {
                notFoundBox.style.display = "none";
                resultBox.style.display = "block";
                document.getElementById("result-name").textContent = data.product_name;
                document.getElementById("result-barcode").textContent = data.barcode || data.sku || "-";
                document.getElementById("result-stock").textContent = data.stock_quantity;
                document.getElementById("result-price").textContent = data.selling_price.toFixed(2);
                document.getElementById("stock-in-link").href =
                `/admin/inventory/stock-in?product_id=${data.product_id}`;
                document.getElementById("stock-out-link").href =
                `/admin/inventory/stock-out?product_id=${data.product_id}`;
            } else {
                resultBox.style.display = "none";
                notFoundBox.style.display = "block";
            }
        })
        .catch(() => {
            resultBox.style.display = "none";
            notFoundBox.style.display = "block";
        });
    }
    manualInput.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
            e.preventDefault();
            lookupCode(manualInput.value.trim());
        }
    });
    if (typeof Html5Qrcode !== "undefined") {
        const scanner = new Html5Qrcode("reader");
        Html5Qrcode.getCameras()
        .then((cameras) => {
            if (cameras && cameras.length) {
                scanner.start(
                {
                    facingMode: "environment"
                },
                {
                    fps: 10, qrbox: 250
                },
                (decodedText) => {
                    manualInput.value = decodedText;
                    lookupCode(decodedText);
                },
                () => {
                }
                // ignore per-frame scan failures
                );
            }
        })
        .catch(() => {
            // No camera available/permitted -- manual input still works.
        });
    }
});
