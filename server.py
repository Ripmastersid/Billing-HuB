import http.server, json, os, uuid, unicodedata, qrcode
from urllib.parse import parse_qs, quote
from io import BytesIO
from fpdf import FPDF

PORTA = 8000
BASE = "http://localhost:8000"
PASTA = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(PASTA, "docs.json")

CSS = """
body{background:#0A0F2C;color:#E8E8E8;font-family:Arial;margin:0;padding:14px}
h2{text-align:center;color:#C0C0C0}
h3{color:#D4AF37;border-bottom:1px solid #D4AF37;padding-bottom:6px}
h4{margin:4px 0}
h5{color:#9aa3b8;margin:2px 0;font-weight:normal}
input,textarea{width:100%;box-sizing:border-box;background:#11182F;border:1px solid #D4AF37;color:#fff;padding:10px;border-radius:6px;margin-bottom:10px}
button{background:#D4AF37;color:#0A0F2C;font-weight:bold;padding:14px;border:none;border-radius:8px;width:100%;margin:4px 0}
button:active,button:hover{background:#7a5c14;color:#fff}
.card{background:#0D1533;border:1px solid #C0C0C0;border-radius:10px;padding:12px;margin-bottom:12px}
.saldo{font-size:26px;color:#D4AF37;font-weight:bold}
img.banner{width:100%;border-radius:10px}
pre{background:#11182F;border:1px solid #D4AF37;border-radius:6px;padding:10px;white-space:pre-wrap;word-break:break-all}
a{color:#D4AF37}
"""

FORM = """<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Billing HuB</title><link rel='icon' href='/img/billingico.png'><style>""" + CSS + """</style></head><body>
<img class='banner' src='/img/bannerforms.png'><h1 style='display:none'>Billing HuB</h1>
<form method='POST' action='/gerar'>
<div class='card'><h3>Dados da empresa</h3>
<h4>Nome da empresa</h4><input name='nome_empresa'>
<h4>Logo (link, opcional)</h4><input name='logo_url'>
<h4>Endereço</h4><input name='endereco'>
<h4>Contato / WhatsApp</h4><input name='whatsapp'>
<h4>Chave Pix</h4><input name='pix_chave'>
<h4>Titular</h4><input name='pix_titular'>
<h4>Cidade</h4><input name='pix_cidade'>
<h4>Link do cartão (opcional)</h4><input name='cartao_link'>
</div>
<div class='card'><h3>Dados do cliente</h3>
<h4>Nome do cobrado</h4><input name='nome_cliente'>
<h4>Contato (opcional)</h4><input name='contato'>
<h4>Dados extras (placa/CPF/pedido)</h4><input name='extras'>
<h4>Especificação / mensagem da cobrança</h4><textarea name='especificacao'></textarea>
<h4>Data</h4><input name='data_doc'>
<h4>Nº doc/OS</h4><input name='num_doc'>
<h4>Total</h4><input name='total' inputmode='decimal'>
<h4>Desconto</h4><input name='desconto'>
<h4>Adiantamento</h4><input name='adiantamento'>
<h4>Vencimento (opcional)</h4><input name='vencimento'>
</div>
<button>GERAR LINK DO DOCUMENTO</button>
</form></body></html>"""

GERADO = """<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Gerado!</title><style>""" + CSS + """</style></head><body>
<img class='banner' src='/img/bannerforms.png'>
<div class='card'><h3>Documento gerado!</h3>
<a href='/doc/__ID__'><button>ABRIR DOCUMENTO</button></a>
<a href='https://wa.me/?text=__MSGWA__'><button>ENVIAR POR WHATSAPP</button></a>
<a href='mailto:?subject=Cobranca&body=__MSGWA__'><button>ENVIAR POR E-MAIL</button></a>
<h5>Link do cobrado: __BASE__/doc/__ID__</h5>
</div></body></html>"""

DOC = """<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Documento</title><style>""" + CSS + """</style></head><body>
<img class='banner' src='/img/pdfbanner.png'>
<h2>__EMPRESA__</h2>
<h5>__ENDERECO__ • __WHATSAPP__</h5>
<div class='card'>
<p>Olá, <b>__NOME__</b>!</p>
<p>__ESPEC__</p>
<h5>__EXTRAS__</h5>
<h5>Data: __DATA__ • Doc/OS: __NUM__ • Vencimento: __VENC__</h5>
<h5>Total: R$ __TOTAL__ | Desconto: R$ __DESC__ | Adiantamento: R$ __ADIA__</h5>
<p class='saldo'>Saldo: R$ __SALDO__</p>
</div>
<div class='card'><h3>Pague com Pix</h3>
<pre id='pix'>__PIX__</pre>
<img src='/qr/__ID__' style='width:70%'>
<button onclick="copiar('pix')">COPIAR PIX</button>
<a href='/pdf/__ID__'><button>BAIXAR PDF</button></a>
</div>
<script>function copiar(q){var t=document.getElementById(q);navigator.clipboard.writeText(t.innerText);alert('Copiado!');}</script>
</body></html>"""

def esc(t): return t.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
def limpar(t,n):
    t = unicodedata.normalize("NFKD", t.upper())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return t[:n]
def tlv(tag,val): return tag + f"{len(val):02d}" + val
def crc16(s):
    crc = 0xFFFF
    for b in s.encode():
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if (crc & 0x8000) else (crc << 1)
            crc &= 0xFFFF
    return f"{crc:04X}"
def pix_payload(chave,nome,cidade,valor):
    p = tlv("00","01") + tlv("01","11")
    p += tlv("26", tlv("00","br.gov.bcb.pix") + tlv("01",chave))
    p += tlv("52","0000") + tlv("53","986") + tlv("54",valor)
    p += tlv("58","BR") + tlv("59",limpar(nome,25)) + tlv("60",limpar(cidade,15))
    p += tlv("62", tlv("05","***")) + "6304"
    return p + crc16(p)
def carregar():
    if os.path.exists(DOCS): return json.load(open(DOCS))
    return {}
def salvar(d): json.dump(d, open(DOCS,"w"))

def montar_doc(d):
    h = DOC
    vals = {"EMPRESA":d.get("nome_empresa",""),"ENDERECO":d.get("endereco",""),"WHATSAPP":d.get("whatsapp",""),"NOME":d.get("nome_cliente",""),"ESPEC":d.get("especificacao",""),"EXTRAS":d.get("extras",""),"DATA":d.get("data_doc",""),"NUM":d.get("num_doc",""),"VENC":d.get("vencimento","") or "sem vencimento","SALDO":d["saldo"],"TOTAL":d.get("total","0"),"DESC":d.get("desconto","0"),"ADIA":d.get("adiantamento","0"),"PIX":d["pix"],"ID":d["id"]}
    for k,v in vals.items(): h = h.replace("__"+k+"__", esc(str(v)))
    return h

def gerar_pdf(d):
    try:
        pdf = FPDF(); pdf.add_page()
        try: pdf.image(os.path.join(PASTA,"pdfbanner.png"), x=0, y=0, w=210)
        except Exception: pass
        pdf.set_y(80)
        pdf.set_font("Helvetica","B",14); pdf.set_text_color(13,27,62)
        pdf.cell(0,8,d.get("nome_empresa","")); pdf.ln()
        pdf.set_font("Helvetica","",9); pdf.set_text_color(90,90,90)
        for t in [d.get("endereco",""), d.get("whatsapp","")]:
            if t: pdf.cell(0,5,t); pdf.ln()
        pdf.ln(3); pdf.set_text_color(0,0,0); pdf.set_font("Helvetica","",11)
        for t in [f"Cliente: {d.get('nome_cliente','')}", f"{d.get('especificacao','')}", f"{d.get('extras','')}", f"Data: {d.get('data_doc','')}   Doc/OS: {d.get('num_doc','')}   Venc.: {d.get('vencimento','') or '---'}", f"Total: {d.get('total','0')}  Desconto: {d.get('desconto','0')}  Adiantamento: {d.get('adiantamento','0')}"]:
            if t.strip(): pdf.multi_cell(0,6,t)
        pdf.ln(3); pdf.set_font("Helvetica","B",20); pdf.set_text_color(180,140,40)
        pdf.cell(0,10,f"SALDO: R$ {d['saldo']}"); pdf.ln()
        pdf.ln(3)
        buf = BytesIO(); qrcode.make(d["pix"]).save(buf,"PNG"); buf.seek(0)
        pdf.image(buf, x=75, w=60)
        pdf.ln(4); pdf.set_font("Courier","",7); pdf.set_text_color(0,0,0)
        pdf.multi_cell(0,4,d["pix"])
        pdf.ln(2); pdf.set_font("Helvetica","",9); pdf.set_text_color(0,0,200)
        pdf.cell(0,5,f"Acesse: {BASE}/doc/{d['id']}"); pdf.ln()
        return pdf.output()
    except Exception:
        pdf = FPDF(); pdf.add_page(); pdf.set_font("Helvetica","",10)
        pdf.multi_cell(0,6,f"{d.get('nome_empresa','')}\nCliente: {d.get('nome_cliente','')}\n{d.get('especificacao','')}\nSALDO: R$ {d['saldo']}\nPix:\n{d['pix']}\nAcesse: {BASE}/doc/{d['id']}")
        return pdf.output()

class H(http.server.BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def out(self,cod,body,tipo="text/html"):
        b = body.encode() if isinstance(body,str) else body
        self.send_response(cod)
        self.send_header("Content-Type",tipo)
        self.send_header("Content-Length",str(len(b)))
        self.end_headers()
        self.wfile.write(b)
    def do_GET(self):
        if self.path == "/": self.out(200,FORM)
        elif self.path.startswith("/img/"):
            self.out(200, open(os.path.join(PASTA,self.path.split("/")[-1]),"rb").read(), "image/png")
        elif self.path.startswith("/qr/"):
            d = carregar().get(self.path.split("/")[-1])
            if not d: return self.out(404,"nao achou")
            buf = BytesIO()
            qrcode.make(d["pix"], image_factory=qrcode.image.svg.SvgPathImage).save(buf)
            self.out(200, buf.getvalue(), "image/svg+xml")
        elif self.path.startswith("/pdf/"):
            d = carregar().get(self.path.split("/")[-1])
            if not d: return self.out(404,"nao achou")
            self.out(200, gerar_pdf(d), "application/pdf")
        elif self.path.startswith("/doc/"):
            d = carregar().get(self.path.split("/")[-1])
            if not d: return self.out(404,"nao achou")
            self.out(200, montar_doc(d))
        else: self.out(404,"nao achou")
    def do_POST(self):
        n = int(self.headers.get("Content-Length",0))
        f = {k:v[0] for k,v in parse_qs(self.rfile.read(n).decode()).items()}
        def num(x):
            try: return float(str(f.get(x,"0")).replace(",","."))
            except Exception: return 0.0
        saldo = num("total") - num("desconto") - num("adiantamento")
        chave = f.get("pix_chave","")
        if chave and chave.isdigit(): chave = "+55" + chave
        payload = pix_payload(chave, f.get("pix_titular","") or f.get("nome_empresa","RECEBEDOR"), f.get("pix_cidade","CIDADE") or "CIDADE", f"{saldo:.2f}")
        uid = uuid.uuid4().hex[:8]
        doc = dict(f); doc.update({"saldo":f"{saldo:.2f}","pix":payload,"id":uid})
        db = carregar(); db[uid] = doc; salvar(db)
        msg = f"Olá, {f.get('nome_cliente','')}! {f.get('nome_empresa','')} enviou sua cobrança ✅\nSaldo: R$ {saldo:.2f}\nVeja e pague aqui: {BASE}/doc/{uid}"
        wa = quote(msg)
        h = GERADO.replace("__ID__",uid).replace("__MSGWA__",wa).replace("__BASE__",BASE)
        self.out(200,h)

if __name__ == "__main__":
    s = http.server.ThreadingHTTPServer(("0.0.0.0",PORTA),H)
    print("Billing HuB no ar! Abra no navegador: http://localhost:8000")
    s.serve_forever()
