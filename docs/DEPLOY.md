# Mettere ClearMarket online 24/7

Serve un server sempre acceso. API, worker, Postgres, Redis e HTTPS girano tutti lì, con
riavvio automatico. Il PC e Docker Desktop non servono più.

| Server | Costo | Nota |
|---|---|---|
| Oracle Cloud Always Free | gratis | Registrazione con carta; disponibilità non garantita; le VM inattive possono essere recuperate |
| VPS economico (Hetzner, OVH, Contabo) | pochi euro al mese | Il più semplice e affidabile |

Render, Railway, Fly.io e Heroku non sono adatti gratis: nessuno offre un worker sempre attivo
senza pagare. Verifica i prezzi attuali prima di scegliere.

## 1. Crea il server

Serve Ubuntu 22.04 o 24.04 con le porte 80 e 443 aperte.

### Oracle Cloud Always Free

1. Registrati su [cloud.oracle.com](https://www.oracle.com/cloud/free/). Scegli con cura la home
   region, perche' poi non si cambia facilmente: va bene Milano o Francoforte, se disponibili.
2. Vai in **Compute > Instances > Create instance**.
3. Come immagine scegli **Canonical Ubuntu 24.04**.
4. Come shape scegli **Ampere VM.Standard.A1.Flex** con **1 OCPU e 3 GB di memoria**.
   Se Oracle risponde "Out of capacity", riprova piu' tardi o usa **VM.Standard.E2.1.Micro**:
   funziona, ma con 1 GB di RAM e una frazione di CPU e' molto piu' lenta.
5. In **Networking** lascia attivo l'indirizzo IPv4 pubblico.
6. In **Add SSH keys** scegli **Paste public keys** e incolla la chiave pubblica.
7. A VM creata apri la **subnet** dell'istanza, poi la **Security List**, e aggiungi due
   Ingress Rule: sorgente `0.0.0.0/0`, TCP, porta di destinazione `80` e poi `443`.

Il limite gratuito attuale e' documentato da
[Oracle](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm).

**Rischio da conoscere:** Oracle puo' recuperare le istanze gratuite inattive. Conta come
inattiva una VM con CPU, rete e, per le A1, memoria tutte sotto il 20% per 7 giorni. ClearMarket
usa poche risorse, quindi una VM piccola da 3 GB tiene la memoria piu' alta rispetto a una da 12
GB, ma non e' una garanzia. Tieni un backup e un controllo esterno su `/healthz`.

### Altri server

Almeno 1 GB di RAM e 20 GB di disco. Con meno di 2 GB lo script attiva lo swap.

## 2. Copia il progetto e avvialo

Dal PC, nella cartella `ClearMarket`, sostituendo utente e IP:

```bash
ssh ubuntu@IP-DEL-SERVER mkdir -p clearmarket && scp -r backend deploy ubuntu@IP-DEL-SERVER:clearmarket/
```

Sul server:

```bash
cd ~/clearmarket && sudo DEEPL_API_KEY=la-tua-chiave bash deploy/install.sh
```

Alla fine lo script stampa `API_BASE_URL` e `DEV_JWT`. Le chiavi si possono cambiare dopo in
`deploy/.env`. L'indirizzo predefinito è `<ip>.sslip.io`, che dà un HTTPS valido senza
comprare un dominio; se l'IP del server cambia, cambia anche l'indirizzo.

## 3. Compila l'APK definitivo

Salva i due valori in `mobile/config/prod.json`, come in `dev.json.example`, poi dalla
cartella `mobile`:

```bash
flutter build apk --release --split-per-abi --dart-define-from-file=config/prod.json
```

L'APK per quasi tutti i telefoni è `build/app/outputs/flutter-apk/app-arm64-v8a-release.apk`.
È firmato con la chiave di debug: va bene da installare a mano, non per il Play Store.

## Manutenzione

| Operazione | Comando, sul server |
|---|---|
| Stato | `sudo docker compose --env-file deploy/.env -f deploy/docker-compose.prod.yml ps` |
| Log del worker | stesso comando, con `logs -f worker` al posto di `ps` |
| Aggiornamento | ricopia i file e rilancia `sudo bash deploy/install.sh` |
| Backup | `sudo docker exec clearmarket-postgres-1 pg_dump -U clearmarket clearmarket > backup.sql` |

Lo script non configura backup automatici né allarmi. Attiva gli snapshot del provider, se
disponibili, e un controllo esterno gratuito su `https://<dominio>/healthz`.

## Limiti di questa configurazione

- **Un server solo:** se si ferma, l'app non si aggiorna finché non riparte.
- **Watchlist condivisa:** tutte le copie dell'APK usano lo stesso token. Per un'app pubblica
  serve Supabase Auth, descritto nel [README](../README.md).
- **Licenze:** per un'app distribuita ad altri vanno verificate, come in
  [ARCHITECTURE.md](ARCHITECTURE.md) §7.
