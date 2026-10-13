package com.meltedlamp.toenglish;

import android.content.res.AssetManager;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

final class Translator {
    private static final String GOOGLE = "https://translate.googleapis.com/translate_a/single";
    private static final int MAX_CHARS = 12000;
    private static final int CHUNK = 3500;

    private static JSONObject names = new JSONObject();

    private Translator() {}

    static void loadNames(AssetManager assets) {
        try (InputStream input = assets.open("languages.json")) {
            ByteArrayOutputStream buffer = new ByteArrayOutputStream();
            byte[] piece = new byte[4096];
            int count;
            while ((count = input.read(piece)) >= 0) {
                buffer.write(piece, 0, count);
            }
            names = new JSONObject(buffer.toString(StandardCharsets.UTF_8.name()));
        } catch (Exception ignored) {
            names = new JSONObject();
        }
    }

    static String translate(String text) throws Exception {
        return translate(text, "auto", "en");
    }

    static String translate(String text, String source, String target) throws Exception {
        return translate(text, source, target, true);
    }

    private static String translate(String text, String source, String target, boolean retry) throws Exception {
        if (text == null) text = "";
        text = text.trim();
        if (source == null || source.isEmpty() || (!"auto".equals(source) && !names.has(source))) {
            source = "auto";
        }
        if (target == null || target.isEmpty() || (names.length() > 0 && !names.has(target))) {
            target = "en";
        }
        if (text.isEmpty()) {
            return error("Enter some text to translate.");
        }
        if (text.length() > MAX_CHARS) {
            return error("Keep it under " + String.format("%,d", MAX_CHARS) + " characters.");
        }
        String original = text;
        org.json.JSONArray fixes = new org.json.JSONArray();
        if ("en".equals(source)) {
            Brain.Outcome studied = Brain.study(text);
            text = studied.text;
            fixes = studied.fixes;
        }
        List<Piece> pieces = new ArrayList<>();
        for (String part : split(text)) {
            pieces.add(translateChunk(part, source, target));
        }
        Piece best = pieces.get(0);
        for (Piece piece : pieces) {
            if (piece.weight > best.weight) best = piece;
        }
        StringBuilder translated = new StringBuilder();
        for (Piece piece : pieces) translated.append(piece.translation);
        String joined = translated.toString().trim();
        String targetName = languageName(target);
        if (joined.isEmpty()) {
            return error("No " + targetName + " translation came back.");
        }
        if (retry && !"en".equals(source) && sameLanguage(best.code, "en")) {
            Brain.Outcome studied = Brain.study(original);
            fixes = joinFixes(fixes, studied.fixes);
            if (!studied.text.equals(original) && !sameLanguage(best.code, target)) {
                try {
                    JSONObject parsed = new JSONObject(translate(studied.text, "en", target, false));
                    JSONArray inner = new JSONArray();
                    JSONObject brain = parsed.optJSONObject("brain");
                    if (brain != null && brain.optJSONArray("fixes") != null) inner = brain.optJSONArray("fixes");
                    JSONArray merged = joinFixes(studied.fixes, inner);
                    parsed.put("brain", Brain.snapshot(merged));
                    String learned = Brain.noteFor(merged);
                    String existing = parsed.optString("note", "");
                    if (!learned.isEmpty() && !existing.contains("Brain kept")) {
                        parsed.put("note", (existing + " " + learned).trim());
                    }
                    return parsed.toString();
                } catch (Exception ignored) {
                    /* Keep the first translation if the corrected line cannot be sent. */
                }
            }
        }
        if ("en".equals(target)) {
            Brain.Outcome studied = Brain.study(joined);
            joined = studied.text;
            fixes = joinFixes(fixes, studied.fixes);
        }
        String note = "";
        if (sameLanguage(best.code, target)) {
            note = "This already looks like " + targetName + ".";
        } else if ("en".equals(source) && best.code != null && !best.code.isEmpty() && !sameLanguage(best.code, "en")) {
            note = "That was read as " + languageName(best.code) + ", not English.";
        } else if ("auto".equals(source) && best.confidence != null && best.confidence < 0.35) {
            note = "Low confidence. A very short line can be hard to place.";
        }
        String learned = Brain.noteFor(fixes);
        if (!learned.isEmpty()) note = (note + " " + learned).trim();
        JSONObject result = new JSONObject();
        result.put("translation", joined);
        if ("en".equals(target)) result.put("english", joined);
        result.put("language", languageName(best.code));
        result.put("code", best.code);
        result.put("target", targetName);
        result.put("targetCode", target);
        if (best.confidence != null) result.put("confidence", best.confidence);
        result.put("note", note);
        result.put("brain", Brain.snapshot(fixes));
        return result.toString();
    }

    private static org.json.JSONArray joinFixes(org.json.JSONArray first, org.json.JSONArray second) {
        org.json.JSONArray joined = new org.json.JSONArray();
        if (first != null) {
            for (int i = 0; i < first.length(); i++) joined.put(first.opt(i));
        }
        if (second != null) {
            for (int i = 0; i < second.length(); i++) joined.put(second.opt(i));
        }
        return joined;
    }

    static boolean knownLanguage(String code) {
        return code != null && names.has(code);
    }

    static List<String> languageCodes() {
        List<String> codes = new ArrayList<>();
        java.util.Iterator<String> keys = names.keys();
        while (keys.hasNext()) codes.add(keys.next());
        return codes;
    }

    private static String error(String message) {
        try {
            return new JSONObject().put("error", message).toString();
        } catch (Exception ex) {
            return "{\"error\":\"Translation failed.\"}";
        }
    }

    private static boolean sameLanguage(String detected, String target) {
        if (detected == null || detected.isEmpty() || target == null || target.isEmpty()) return false;
        if (detected.equals(target)) return true;
        if (!target.contains("-") && detected.split("-")[0].equals(target)) return true;
        return false;
    }

    static String languageName(String code) {
        if (code == null || code.isEmpty()) return "Unknown";
        String name = names.optString(code, "");
        if (!name.isEmpty()) return name;
        int dash = code.indexOf('-');
        String base = dash > 0 ? code.substring(0, dash) : code;
        name = names.optString(base, "");
        return name.isEmpty() ? code : name;
    }

    private static List<String> split(String text) {
        List<String> parts = new ArrayList<>();
        if (text.length() <= CHUNK) {
            parts.add(text);
            return parts;
        }
        int start = 0;
        while (start < text.length()) {
            int end = Math.min(start + CHUNK, text.length());
            if (end < text.length()) {
                int breakAt = text.substring(start, end).lastIndexOf('\n');
                if (breakAt > CHUNK / 4) end = start + breakAt + 1;
            }
            parts.add(text.substring(start, end));
            start = end;
        }
        return parts;
    }

    private static Piece translateChunk(String text, String source, String target) throws Exception {
        String body = "client=" + enc("gtx")
                + "&sl=" + enc(source)
                + "&tl=" + enc(target)
                + "&dt=" + enc("t")
                + "&dj=" + enc("1")
                + "&q=" + enc(text);
        byte[] payload = body.getBytes(StandardCharsets.UTF_8);
        HttpURLConnection connection = (HttpURLConnection) new URL(GOOGLE).openConnection();
        connection.setRequestMethod("POST");
        connection.setDoOutput(true);
        connection.setConnectTimeout(25000);
        connection.setReadTimeout(25000);
        connection.setRequestProperty("User-Agent", "Mozilla/5.0");
        connection.setRequestProperty("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8");
        connection.setFixedLengthStreamingMode(payload.length);
        try (OutputStream output = connection.getOutputStream()) {
            output.write(payload);
        }
        int status = connection.getResponseCode();
        InputStream stream = status >= 400 ? connection.getErrorStream() : connection.getInputStream();
        if (status != 200 || stream == null) {
            throw new java.io.IOException("Translator responded " + status);
        }
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        byte[] piece = new byte[4096];
        int count;
        while ((count = stream.read(piece)) >= 0) buffer.write(piece, 0, count);
        stream.close();
        connection.disconnect();
        JSONObject data = new JSONObject(buffer.toString(StandardCharsets.UTF_8.name()));
        JSONArray sentences = data.optJSONArray("sentences");
        StringBuilder translated = new StringBuilder();
        if (sentences != null) {
            for (int i = 0; i < sentences.length(); i++) {
                JSONObject sentence = sentences.optJSONObject(i);
                if (sentence != null && sentence.has("trans")) {
                    translated.append(sentence.optString("trans"));
                }
            }
        }
        Double confidence = null;
        if (data.has("confidence") && !data.isNull("confidence")) {
            confidence = data.optDouble("confidence");
        }
        return new Piece(translated.toString(), data.optString("src", ""), confidence, text.length());
    }

    private static String enc(String value) throws Exception {
        return URLEncoder.encode(value, "UTF-8");
    }

    private static final class Piece {
        final String translation;
        final String code;
        final Double confidence;
        final int weight;

        Piece(String translation, String code, Double confidence, int weight) {
            this.translation = translation;
            this.code = code;
            this.confidence = confidence;
            this.weight = weight;
        }
    }
}
