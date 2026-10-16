<p align="center">
  <img src="https://raw.githubusercontent.com/emmea90/caleffi-code-home-assistant/main/custom_components/caleffi_code/brand/icon.png" alt="Caleffi CODE" width="128">
</p>

# Caleffi CODE per Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![Licenza: MIT](https://img.shields.io/badge/Licenza-MIT-blue.svg)](LICENSE)

Integrazione personalizzata per Home Assistant che collega il tuo account **Caleffi CODE** e controlla il riscaldamento zona per zona.

> **Disclaimer:** progetto non ufficiale, non affiliato né approvato da Caleffi. "Caleffi" e "CODE" sono marchi dei rispettivi proprietari. Usalo a tuo rischio.

## Funzionalità

Per ogni zona del tuo impianto vengono create automaticamente:

- **Termostato (`climate`)**: temperatura attuale, temperatura obiettivo, modalità `Auto`, `Riscaldamento` (manuale) e `Spento`, più i preset Caleffi.
- **Sensore di temperatura (`sensor`)**: temperatura ambiente della zona (°C), con classe di misura adatta a grafici e statistiche a lungo termine.

Dettagli:

| Elemento | Note |
|---|---|
| Preset | `auto`, `eco`, `holiday`, `manual`, `off`, `party`, `cleaning`, `forced_off` |
| Setpoint manuale | Dura 2 ore, come nell'app Caleffi, poi la zona torna al programma |
| Aggiornamento | Ogni 2 minuti (polling cloud) |
| Sessione | Rinnovo ogni 30 minuti; se il token è scaduto, nuovo login con le credenziali salvate |
| Zone nuove | Rilevate automaticamente, senza riavviare |
| Entità sensore | `sensor.caleffi_<nome_zona>_temperatura` |

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

Per segnalare un problema apri una [issue](https://github.com/emmea90/caleffi-code-home-assistant/issues) indicando la versione di Home Assistant e i log (senza credenziali).

## Sviluppo

Il repository segue git flow: `main` contiene le release, `develop` il lavoro in corso.

## Licenza

[MIT](LICENSE)
