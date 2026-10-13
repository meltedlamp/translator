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
        String note = "";
        if (sameLanguage(best.code, target)) {
            note = "This already looks like " + targetName + ".";
        } else if ("en".equals(source) && best.code != null && !best.code.isEmpty() && !sameLanguage(best.code, "en")) {
            note = "That was read as " + languageName(best.code) + ", not English.";
        } else if ("auto".equals(source) && best.confidence != null && best.confidence < 0.35) {
            note = "Low confidence. A very short line can be hard to place.";
        }
        JSONObject result = new JSONObject();
        result.put("translation", joined);
        if ("en".equals(target)) result.put("english", joined);
        result.put("language", languageName(best.code));
        result.put("code", best.code);
        result.put("target", targetName);
        result.put("targetCode", target);
        if (best.confidence != null) result.put("confidence", best.confidence);
        result.put("note", note);
        return result.toString();
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
