<p align="center">
  <img src="https://raw.githubusercontent.com/emmea90/caleffi-code-home-assistant/main/custom_components/caleffi_code/brand/icon.png" alt="Caleffi CODE" width="128">
</p>

# Caleffi CODE per Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![Licenza: MIT](https://img.shields.io/badge/Licenza-MIT-blue.svg)](LICENSE)

Integrazione personalizzata per Home Assistant che collega il tuo account **Caleffi CODE** e controlla il riscaldamento zona per zona.

> **Disclaimer:** progetto non ufficiale, non affiliato né approvato da Caleffi. Può comandare il riscaldamento. L'uso è a tuo rischio. Leggi le [note legali](#note-legali) prima di installarlo.

## Funzionalità

Per ogni zona del tuo impianto vengono create automaticamente:

- **Termostato (`climate`)**: temperatura attuale, temperatura obiettivo, modalità `Auto`, `Riscaldamento` (manuale) e `Spento`, più i preset Caleffi.
- **Testina (`cover`)**: comandi separati per aprirla e chiuderla, con la posizione riportata dall'apertura effettiva quando disponibile.
- **Sensore di temperatura (`sensor`)**: temperatura ambiente della zona (°C), con classe di misura adatta a grafici e statistiche a lungo termine.
- **Sensore di stato della testina (`sensor`)**: `Aperto` o `Chiuso`, con la percentuale di apertura riportata come attributo quando disponibile.
- **Programmazione settimanale (`sensor`)**: fasce orarie e temperature di ogni giorno negli attributi `programmazione`.
- **Switch dei comandi `+`/`−` (`switch`)**: abilita o disabilita la regolazione manuale dalla testina; non apre né chiude la valvola.

Dettagli:

| Elemento | Note |
|---|---|
| Preset | `auto`, `eco`, `holiday`, `manual`, `off`, `party`, `cleaning`, `forced_off` |
| Setpoint manuale | Dura 2 ore, come nell'app Caleffi, poi la zona torna al programma |
| Aggiornamento | Ogni 2 minuti (polling cloud) |
| Sessione | Rinnovo ogni 30 minuti; se il token è scaduto, nuovo login con le credenziali salvate |
| Zone nuove | Rilevate automaticamente, senza riavviare |
| Entità sensore | `sensor.caleffi_<nome_zona>_temperatura` |

### Modificare la programmazione

Il sensore `sensor.caleffi_<nome_zona>_programmazione_settimanale` contiene l'intera settimana nell'attributo `programmazione`, con un elenco di fasce per ciascun giorno. `ora_fine` indica l'ora alla quale termina la fascia; le temperature sono in °C.

Per sostituire le fasce di un singolo giorno usa l'azione `caleffi_code.set_zone_schedule`. Gli orari devono essere in ordine crescente; il giorno usa la numerazione Caleffi da 1 (domenica) a 7 (sabato). Ogni fascia definisce l'orario di fine e la temperatura fino alla fascia successiva:

```yaml
action: caleffi_code.set_zone_schedule
data:
  gateway_serial: "SERIALE_GATEWAY"
  zone_id: "1"
  day: 2
  slots:
    - time: "06:30"
      temperature: 20
    - time: "08:00"
      temperature: 17
    - time: "18:00"
      temperature: 20
    - time: "22:30"
      temperature: 17
```

Il servizio sostituisce la programmazione dell'intero giorno, non solo le fasce indicate. Gli orari validi vanno da `00:01` a `24:00`; le temperature devono rispettare i limiti configurati sul gateway.

Puoi copiare l'intera settimana da una zona a un'altra con `caleffi_code.copy_zone_schedule`:

```yaml
action: caleffi_code.copy_zone_schedule
data:
  source_gateway_serial: "SERIALE_GATEWAY"
  source_zone_id: "1"
  target_gateway_serial: "SERIALE_GATEWAY"
  target_zone_id: "2"
```

Gli scenari vengono salvati nella memoria persistente di Home Assistant. `caleffi_code.save_schedule_scene` salva un giorno (`scope: day` e `day`) oppure la settimana completa (`scope: week`). Puoi fornire direttamente le fasce con `slots`/`days` oppure acquisirle dalla programmazione attuale indicando `gateway_serial` e `zone_id`. Se il nome esiste già, occorre impostare `overwrite: true` per sostituirlo. Per definire direttamente uno scenario per il lunedì:

```yaml
action: caleffi_code.save_schedule_scene
data:
  name: "Mattina invernale"
  scope: day
  day: 2
  slots:
    - time: "06:30"
      temperature: 20
    - time: "08:00"
      temperature: 17
```

Per acquisire invece il giorno già programmato in una stanza, ometti `slots` e specifica gateway e zona. Per uno scenario settimanale definito direttamente usa `scope: week` e `days`, una mappa con le chiavi `1`-`7` (domenica-sabato) e una lista `time`/`temperature` per ciascun giorno.

Applica uno scenario con `caleffi_code.apply_schedule_scene`. Per uno scenario giornaliero puoi specificare un altro `day` per applicarlo a un giorno diverso; se omesso, viene usato il giorno originale. Gli scenari settimanali applicano tutti e sette i giorni:

```yaml
action: caleffi_code.apply_schedule_scene
data:
  name: "Inverno"
  gateway_serial: "SERIALE_GATEWAY"
  zone_id: "2"
```

La copia e l'applicazione di scenari settimanali inviano gli aggiornamenti un giorno alla volta. Se il cloud rifiuta una richiesta durante l'operazione, i giorni precedenti potrebbero essere già stati aggiornati.

## Installazione

### HACS (consigliata)

1. In HACS apri **⋮ → Repository personalizzati**.
2. Aggiungi `https://github.com/emmea90/caleffi-code-home-assistant` con categoria **Integrazione**.
3. Cerca **Caleffi CODE** e premi **Scarica**.
4. Riavvia Home Assistant.

### Manuale

1. Copia la cartella `custom_components/caleffi_code` nella directory `custom_components` di Home Assistant.
2. Riavvia Home Assistant.

## Configurazione

1. Vai in **Impostazioni → Dispositivi e servizi → Aggiungi integrazione**.
2. Cerca **Caleffi CODE**.
3. Inserisci email e password del tuo account Caleffi.

Email e password restano salvate nella configurazione locale di Home Assistant. L'integrazione rinnova il token da sola: se il refresh token non è più valido, ripete il login con quelle credenziali. Ogni 30 minuti rinnova la sessione anche senza errori. Se le credenziali non sono più accettate, Home Assistant chiede di inserirle di nuovo.

Se l'integrazione era già configurata prima di questo aggiornamento, completa una volta la richiesta di nuova autenticazione: la password precedente non era stata salvata.

La connessione usa HTTPS con la verifica standard dei certificati TLS.

## Grafici e storico

I sensori di temperatura hanno `state_class: measurement`, quindi funzionano con le schede grafico native di Home Assistant e con le statistiche a lungo termine. Per un archivio esterno (ad esempio InfluxDB) assicurati che le entità `sensor.caleffi_*_temperatura` non siano escluse dai filtri della relativa integrazione.

## Risoluzione dei problemi

- **Richiesta di nuova autenticazione dopo l'aggiornamento:** inserisci di nuovo email e password una sola volta, così l'integrazione può rinnovare il token da sola.
- **Accesso non riuscito:** controlla email e password dell'account Caleffi CODE.
- **Impossibile collegarsi:** verifica la connessione internet di Home Assistant; l'integrazione dipende dal cloud Caleffi.
- **Zone mancanti:** attendi il successivo aggiornamento (2 minuti) o ricarica l'integrazione.
- **Dettagli degli errori:** apri **Impostazioni → Sistema → Registri** e cerca `caleffi_code` o `Caleffi CODE`. Un errore HTTP include metodo e percorso API richiesto; oscura email, seriali e token prima di condividere i log.

Per segnalare un problema apri una [issue](https://github.com/emmea90/caleffi-code-home-assistant/issues) indicando la versione di Home Assistant e i log (senza credenziali).

## Sviluppo

Il repository segue git flow: `main` contiene le release, `develop` il lavoro in corso. Non esiste un ramo `master`.

Per pubblicare una versione allinea `version` in `custom_components/caleffi_code/manifest.json` a `X.Y.Z`, porta quel commit su `main` e invia il tag annotato:

```bash
git tag -a vX.Y.Z -m "Release X.Y.Z"
git push origin vX.Y.Z
```

Il push del tag fa partire da solo GitHub Actions, che crea la release omonima e allega `caleffi_code.zip`. HACS installa quello zip. Il tag deve essere nel formato `vX.Y.Z`, deve coincidere con `manifest.json` e deve puntare a un commit già presente su `main`. L'avvio manuale del workflow resta solo un recupero, con lo stesso nome di tag.

A ogni push e pull request partono anche la validazione HACS e hassfest.

## Note legali

Questo progetto è indipendente e non ufficiale. Non è affiliato, sponsorizzato, autorizzato né approvato da Caleffi S.p.A., da Nabu Casa o dal progetto Home Assistant. "Caleffi", "CODE" e gli altri segni distintivi collegati appartengono ai rispettivi titolari e sono usati solo per indicare l'interoperabilità. "Home Assistant" è un marchio dei rispettivi titolari.

Il software è fornito "così com'è", secondo la [licenza MIT](LICENSE), senza garanzie di alcun tipo, esplicite o implicite, incluse quelle di commerciabilità, idoneità a uno scopo particolare, accuratezza, continuità, sicurezza e non violazione. Non è garantita la compatibilità con versioni future dell'app Caleffi, del cloud Caleffi o di Home Assistant. Il servizio remoto può cambiare, rifiutare l'accesso o smettere di rispondere in qualsiasi momento.

L'integrazione accede all'account Caleffi CODE e può leggere e modificare l'impianto, comprese temperatura, modalità e preset di ogni zona. Un comando sbagliato, un ritardo, una lettura non aggiornata, un errore del software o un cambiamento del cloud possono lasciare una zona accesa, spenta o a una temperatura diversa da quella voluta, con effetti su comfort, consumi, impianto e abitazione. Questo software non sostituisce l'app ufficiale, i comandi sull'impianto né un installatore qualificato. Controlla sull'app Caleffi che lo stato reale sia quello atteso, e mantieni un modo per comandare l'impianto anche se Home Assistant o questa integrazione non rispondono.

Email e password restano nella configurazione locale di Home Assistant e sono inviate solo al cloud Caleffi per l'accesso. L'autore non le riceve e non mette in mezzo un proprio server. Sei tu responsabile della custodia di quelle credenziali, del rispetto delle condizioni d'uso di Caleffi e di Home Assistant, e della scelta di usare un client non ufficiale.

Nei limiti massimi consentiti dalla legge, l'autore e i collaboratori non rispondono di danni diretti, indiretti, incidentali, consequenziali o speciali, né di perdita di dati, maggiori consumi, disservizi, blocco dell'account, danni a cose o persone, derivanti dall'uso o dall'impossibilità di usare questo software, anche se era stata segnalata la possibilità di quei danni. Lo installi e lo usi a tuo esclusivo rischio.

Queste note non escludono la responsabilità per dolo o colpa grave, né qualsiasi altra responsabilità che la legge applicabile non permette di escludere o limitare. Se non le accetti, non installare e non usare l'integrazione.

## Licenza

[MIT](LICENSE)
