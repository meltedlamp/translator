package com.meltedlamp.toenglish;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashSet;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Grammar brain that stays in the app's files on this device.
 * Factory rules ship with the app. Lessons the text teaches are written beside them.
 */
final class Brain {
    private static final int MAX_LESSONS = 1500;
    private static final int MAX_SPAN = 80;

    private static final String[][] PHRASES = {
            {"your welcome", "you're welcome"},
            {"could of", "could have"},
            {"should of", "should have"},
            {"would of", "would have"},
            {"must of", "must have"},
            {"more better", "better"},
            {"more easier", "easier"},
            {"more harder", "harder"},
            {"return back", "return"},
            {"revert back", "revert"},
            {"their is", "there is"},
            {"their are", "there are"},
            {"their was", "there was"},
            {"their were", "there were"},
            {"their going", "they're going"},
            {"their not", "they're not"},
            {"there going", "they're going"},
            {"there not", "they're not"},
            {"your going", "you're going"},
            {"your not", "you're not"},
            {"your the", "you're the"},
            {"your a", "you're a"},
            {"your an", "you're an"},
            {"its a", "it's a"},
            {"its the", "it's the"},
            {"its not", "it's not"},
            {"its been", "it's been"},
            {"eachother", "each other"},
            {"infront of", "in front of"},
            {"infront", "in front"},
            {"eventhough", "even though"},
            {"aswell", "as well"},
            {"atleast", "at least"},
    };

    private static final String[][] WORDS = {
            {"dont", "don't"},
            {"doesnt", "doesn't"},
            {"didnt", "didn't"},
            {"cant", "can't"},
            {"wont", "won't"},
            {"isnt", "isn't"},
            {"arent", "aren't"},
            {"wasnt", "wasn't"},
            {"werent", "weren't"},
            {"hasnt", "hasn't"},
            {"havent", "haven't"},
            {"hadnt", "hadn't"},
            {"wouldnt", "wouldn't"},
            {"couldnt", "couldn't"},
            {"shouldnt", "shouldn't"},
            {"youre", "you're"},
            {"theyre", "they're"},
            {"im", "I'm"},
            {"ive", "I've"},
            {"youve", "you've"},
            {"theyve", "they've"},
            {"weve", "we've"},
            {"thats", "that's"},
            {"whats", "what's"},
            {"theres", "there's"},
            {"heres", "here's"},
            {"alot", "a lot"},
            {"noone", "no one"},
    };

    private static final Pattern I_WORD = Pattern.compile("(?<![\\w.])i(?![\\w.])");

    private static final String[][] AGREEMENT = {
            {"\\b(he|she|it) don't\\b", "$1 doesn't"},
            {"\\b(he|she|it) dont\\b", "$1 doesn't"},
            {"\\b(we|they|you) was\\b", "$1 were"},
            {"\\b(we|they|you) is\\b", "$1 are"},
            {"\\b(we|they|you) has\\b", "$1 have"},
            {"\\b(I|we|they|you) doesn't\\b", "$1 don't"},
    };

    private static final Pattern DOUBLED = Pattern.compile(
            "\\b(the|a|an|and|to|of|in|on|for)\\s+\\1\\b",
            Pattern.CASE_INSENSITIVE
    );
    private static final Pattern ARTICLE = Pattern.compile(
            "\\b(a|an)\\s+([A-Za-z][A-Za-z']*)",
            Pattern.CASE_INSENSITIVE
    );
    private static final Set<String> TAKES_A = new HashSet<>();

    static {
        Collections.addAll(
                TAKES_A,
                "one", "once", "university", "uniform", "union", "unique", "unit", "united",
                "user", "usual", "usually", "useful", "european", "euro", "eulogy", "utensil",
                "unicorn", "universal", "universe", "unanimous"
        );
    }

    private static File file;

    private Brain() {}

    static final class Outcome {
        final String text;
        final JSONArray fixes;

        Outcome(String text, JSONArray fixes) {
            this.text = text;
            this.fixes = fixes;
        }
    }

    static synchronized void open(File dir) {
        if (dir == null) return;
        if (!dir.exists()) dir.mkdirs();
        file = new File(dir, "brain.json");
        if (!file.exists()) save(empty());
    }

    static synchronized Outcome study(String text) {
        if (text == null || text.trim().isEmpty() || !text.matches("(?s).*[A-Za-z].*")) {
            return new Outcome(text == null ? "" : text, new JSONArray());
        }
        text = text.replace('\u2019', '\'').replace('\u2018', '\'');
        JSONObject lessons = load().optJSONObject("lessons");
        if (lessons == null) lessons = new JSONObject();
        JSONArray fixes = new JSONArray();
        text = applyLessons(text, lessons, fixes);
        text = applyPhrases(text, fixes);
        text = applyWords(text, fixes);
        text = applyAgreement(text, fixes);
        text = applyDoubles(text, fixes);
        text = applyArticles(text, fixes);
        if (fixes.length() > 0) remember(fixes);
        return new Outcome(text, unique(fixes));
    }

    static synchronized JSONObject teach(String before, String after) {
        JSONObject lesson = lessonFrom(before, after);
        if (lesson != null) {
            JSONArray fixes = new JSONArray();
            fixes.put(lesson);
            remember(fixes);
        }
        JSONObject payload = status();
        try {
            payload.put("lesson", lesson == null ? JSONObject.NULL : lesson);
        } catch (Exception ignored) {
        }
        return payload;
    }

    static synchronized JSONObject status() {
        JSONObject lessons = load().optJSONObject("lessons");
        int count = 0;
        int seen = 0;
        if (lessons != null) {
            Iterator<String> keys = lessons.keys();
            while (keys.hasNext()) {
                JSONObject item = lessons.optJSONObject(keys.next());
                count += 1;
                if (item != null) seen += item.optInt("seen", 1);
            }
        }
        JSONObject payload = new JSONObject();
        try {
            payload.put("lessons", count);
            payload.put("seen", seen);
            payload.put("fixes", new JSONArray());
        } catch (Exception ignored) {
        }
        return payload;
    }

    static JSONObject snapshot(JSONArray fixes) {
        JSONObject payload = status();
        try {
            payload.put("fixes", unique(fixes));
        } catch (Exception ignored) {
        }
        return payload;
    }

    static String noteFor(JSONArray fixes) {
        JSONArray unique = unique(fixes);
        if (unique.length() == 0) return "";
        if (unique.length() == 1) {
            JSONObject fix = unique.optJSONObject(0);
            if (fix == null) return "";
            return "Brain kept “" + fix.optString("wrong") + "” → “" + fix.optString("right") + "” on this device.";
        }
        return "Brain kept " + unique.length() + " grammar fixes on this device.";
    }

    private static JSONObject lessonFrom(String before, String after) {
        if (before == null || after == null) return null;
        before = before.replace('\u2019', '\'').replace('\u2018', '\'').trim();
        after = after.replace('\u2019', '\'').replace('\u2018', '\'').trim();
        if (before.isEmpty() || after.isEmpty() || before.equals(after)) return null;
        if (before.length() > 12000 || after.length() > 12000) return null;
        int limit = Math.min(before.length(), after.length());
        int prefix = 0;
        while (prefix < limit && before.charAt(prefix) == after.charAt(prefix)) prefix += 1;
        int suffix = 0;
        while (suffix < limit - prefix && before.charAt(before.length() - 1 - suffix) == after.charAt(after.length() - 1 - suffix)) {
            suffix += 1;
        }
        while (prefix > 0 && !isSpace(before.charAt(prefix - 1))) prefix -= 1;
        while (suffix > 0 && !isSpace(before.charAt(before.length() - suffix))) suffix -= 1;
        int beforeEnd = before.length() - suffix;
        int afterEnd = after.length() - suffix;
        if (beforeEnd < prefix) beforeEnd = prefix;
        if (afterEnd < prefix) afterEnd = prefix;
        String wrong = before.substring(prefix, beforeEnd).trim().replaceAll("\\s+", " ");
        String right = after.substring(prefix, afterEnd).trim().replaceAll("\\s+", " ");
        if (wrong.isEmpty() || right.isEmpty() || wrong.equalsIgnoreCase(right)) return null;
        if (wrong.length() > MAX_SPAN || right.length() > MAX_SPAN) return null;
        if (wrong.split("\\s+").length > 8 || right.split("\\s+").length > 8) return null;
        if (!wrong.matches(".*[A-Za-z].*") || !right.matches(".*[A-Za-z].*")) return null;
        if (!related(wrong, right)) return null;
        String[] scoped = attachNeighbor(before, after, prefix, suffix, wrong, right);
        wrong = scoped[0];
        right = scoped[1];
        if (tooBroad(wrong, right)) return null;
        JSONObject lesson = new JSONObject();
        try {
            lesson.put("wrong", wrong);
            lesson.put("right", right);
            lesson.put("from", "edit");
        } catch (Exception ignored) {
        }
        return lesson;
    }

    private static boolean tooBroad(String wrong, String right) {
        if (wrong.contains(" ") || right.contains(" ")) return false;
        String left = wrong.toLowerCase(Locale.US);
        String other = right.toLowerCase(Locale.US);
        boolean grew = other.startsWith(left) || left.startsWith(other);
        return grew && Math.abs(left.length() - other.length()) > 0 && left.length() <= 4;
    }

    private static String[] attachNeighbor(String before, String after, int prefix, int suffix, String wrong, String right) {
        if (!tooBroad(wrong, right)) return new String[]{wrong, right};
        String lead = before.substring(0, prefix).trim();
        if (!lead.isEmpty()) {
            String[] parts = lead.split("\\s+");
            String neighbor = parts[parts.length - 1];
            return new String[]{neighbor + " " + wrong, neighbor + " " + right};
        }
        String trail = suffix > 0 ? before.substring(before.length() - suffix).trim() : "";
        if (!trail.isEmpty()) {
            String neighbor = trail.split("\\s+")[0];
            return new String[]{wrong + " " + neighbor, right + " " + neighbor};
        }
        return new String[]{wrong, right};
    }

    private static boolean related(String wrong, String right) {
        String left = wrong.toLowerCase(Locale.US);
        String other = right.toLowerCase(Locale.US);
        if (left.replaceAll("[^a-z]", "").equals(other.replaceAll("[^a-z]", ""))) return true;
        if ((left.startsWith(other) || other.startsWith(left)) && Math.abs(left.length() - other.length()) <= 3) {
            return true;
        }
        int match = 0;
        int limit = Math.min(left.length(), other.length());
        for (int i = 0; i < limit; i++) {
            if (left.charAt(i) == other.charAt(i)) match += 1;
        }
        double ratio = (2.0 * match) / (left.length() + other.length());
        return ratio >= 0.72;
    }

    private static String applyPhrases(String text, JSONArray fixes) {
        List<String[]> ordered = new ArrayList<>();
        Collections.addAll(ordered, PHRASES);
        ordered.sort((a, b) -> Integer.compare(b[0].length(), a[0].length()));
        for (String[] pair : ordered) {
            text = swap(phrase(pair[0]), pair[1], pair[1], text, fixes, false);
        }
        return text;
    }

    private static String applyWords(String text, JSONArray fixes) {
        for (String[] pair : WORDS) {
            text = swap(phrase(pair[0]), pair[1], pair[1], text, fixes, false);
        }
        return swap(I_WORD, "I", "I", text, fixes, false);
    }

    private static String applyAgreement(String text, JSONArray fixes) {
        for (String[] pair : AGREEMENT) {
            text = swap(Pattern.compile(pair[0], Pattern.CASE_INSENSITIVE), pair[1], null, text, fixes, true);
        }
        return text;
    }

    private static String applyDoubles(String text, JSONArray fixes) {
        Matcher matcher = DOUBLED.matcher(text);
        StringBuffer buffer = new StringBuffer();
        while (matcher.find()) {
            String word = matcher.group(1);
            addFix(fixes, matcher.group(), word, word.toLowerCase(Locale.US));
            matcher.appendReplacement(buffer, Matcher.quoteReplacement(word));
        }
        matcher.appendTail(buffer);
        return buffer.toString();
    }

    private static String applyArticles(String text, JSONArray fixes) {
        Matcher matcher = ARTICLE.matcher(text);
        StringBuffer buffer = new StringBuffer();
        while (matcher.find()) {
            String article = matcher.group(1);
            String word = matcher.group(2);
            Boolean needed = needsAn(word);
            if (needed == null) {
                matcher.appendReplacement(buffer, Matcher.quoteReplacement(matcher.group()));
                continue;
            }
            String want = needed ? "an" : "a";
            if (article.equalsIgnoreCase(want)) {
                matcher.appendReplacement(buffer, Matcher.quoteReplacement(matcher.group()));
                continue;
            }
            String fixedArticle = matchCase(article, want);
            String right = fixedArticle + " " + word;
            addFix(fixes, matcher.group(), right, want + " " + word.toLowerCase(Locale.US));
            matcher.appendReplacement(buffer, Matcher.quoteReplacement(right));
        }
        matcher.appendTail(buffer);
        return buffer.toString();
    }

    private static String applyLessons(String text, JSONObject lessons, JSONArray fixes) {
        List<String> keys = new ArrayList<>();
        Iterator<String> iterator = lessons.keys();
        while (iterator.hasNext()) keys.add(iterator.next());
        keys.sort((a, b) -> Integer.compare(b.length(), a.length()));
        for (String key : keys) {
            JSONObject item = lessons.optJSONObject(key);
            if (item == null) continue;
            String right = item.optString("right", "");
            if (right.isEmpty()) continue;
            text = swap(phrase(key), right, right, text, fixes, false);
        }
        return text;
    }

    private static String swap(Pattern pattern, String repl, String canonical, String text, JSONArray fixes, boolean expand) {
        Matcher matcher = pattern.matcher(text);
        StringBuffer buffer = new StringBuffer();
        while (matcher.find()) {
            String wrong = matcher.group();
            String expanded = repl;
            if (expand) expanded = pattern.matcher(wrong).replaceAll(repl);
            String right = matchCase(wrong, expanded);
            if (wrong.equals(right)) {
                matcher.appendReplacement(buffer, Matcher.quoteReplacement(wrong));
                continue;
            }
            String canon = canonical != null ? canonical : canonFromSample(wrong, expanded);
            addFix(fixes, wrong, right, canon);
            matcher.appendReplacement(buffer, Matcher.quoteReplacement(right));
        }
        matcher.appendTail(buffer);
        return buffer.toString();
    }

    private static void addFix(JSONArray fixes, String wrong, String right, String canonical) {
        JSONObject fix = new JSONObject();
        try {
            fix.put("wrong", wrong);
            fix.put("right", right);
            fix.put("canonical", canonical);
            fixes.put(fix);
        } catch (Exception ignored) {
        }
    }

    private static void remember(JSONArray fixes) {
        JSONObject data = load();
        JSONObject lessons = data.optJSONObject("lessons");
        if (lessons == null) {
            lessons = new JSONObject();
            try {
                data.put("lessons", lessons);
            } catch (Exception ignored) {
            }
        }
        long now = System.currentTimeMillis() / 1000L;
        for (int i = 0; i < fixes.length(); i++) {
            JSONObject fix = fixes.optJSONObject(i);
            if (fix == null) continue;
            String key = fix.optString("wrong", "").trim().toLowerCase(Locale.US).replaceAll("\\s+", " ");
            String right;
            if ("edit".equals(fix.optString("from"))) {
                right = fix.optString("right", "").trim().replaceAll("\\s+", " ");
            } else {
                right = fix.optString("canonical", fix.optString("right", "")).trim().replaceAll("\\s+", " ");
            }
            if (key.isEmpty() || right.isEmpty() || key.equals(right.toLowerCase(Locale.US)) || key.equals("i")) continue;
            if (key.length() > MAX_SPAN || right.length() > MAX_SPAN) continue;
            JSONObject current = lessons.optJSONObject(key);
            try {
                if (current != null) {
                    current.put("seen", current.optInt("seen", 1) + 1);
                    current.put("at", now);
                    if ("edit".equals(fix.optString("from"))) {
                        current.put("right", right);
                        current.put("from", "edit");
                    }
                    continue;
                }
                JSONObject created = new JSONObject();
                created.put("right", right);
                created.put("seen", 1);
                created.put("from", "edit".equals(fix.optString("from")) ? "edit" : "text");
                created.put("at", now);
                lessons.put(key, created);
            } catch (Exception ignored) {
            }
        }
        if (lessons.length() > MAX_LESSONS) trim(lessons);
        save(data);
    }

    private static void trim(JSONObject lessons) {
        List<JSONObject> ranked = new ArrayList<>();
        Iterator<String> keys = lessons.keys();
        while (keys.hasNext()) {
            String key = keys.next();
            JSONObject item = lessons.optJSONObject(key);
            if (item == null) continue;
            try {
                item.put("_key", key);
            } catch (Exception ignored) {
            }
            ranked.add(item);
        }
        ranked.sort(Comparator.comparingInt((JSONObject item) -> item.optInt("seen", 1))
                .thenComparingLong(item -> item.optLong("at", 0)));
        int extra = lessons.length() - MAX_LESSONS;
        for (int i = 0; i < extra && i < ranked.size(); i++) {
            lessons.remove(ranked.get(i).optString("_key"));
        }
        for (JSONObject item : ranked) item.remove("_key");
    }

    private static JSONArray unique(JSONArray fixes) {
        JSONArray ordered = new JSONArray();
        if (fixes == null) return ordered;
        Set<String> seen = new HashSet<>();
        for (int i = 0; i < fixes.length(); i++) {
            JSONObject fix = fixes.optJSONObject(i);
            if (fix == null) continue;
            String wrong = fix.optString("wrong");
            String right = fix.optString("right");
            String key = wrong.toLowerCase(Locale.US) + "\n" + right;
            if (!seen.add(key)) continue;
            JSONObject plain = new JSONObject();
            try {
                plain.put("wrong", wrong);
                plain.put("right", right);
                ordered.put(plain);
            } catch (Exception ignored) {
            }
        }
        return ordered;
    }

    private static Boolean needsAn(String word) {
        if (word.equals(word.toUpperCase(Locale.US)) && word.length() >= 2 && word.length() <= 6) return null;
        String lower = word.toLowerCase(Locale.US);
        if (lower.startsWith("hour") || lower.startsWith("honest") || lower.startsWith("honor")
                || lower.startsWith("honour") || lower.startsWith("heir")) {
            return true;
        }
        if (TAKES_A.contains(lower)) return false;
        char first = lower.charAt(0);
        return first == 'a' || first == 'e' || first == 'i' || first == 'o' || first == 'u';
    }

    private static String matchCase(String sample, String replacement) {
        if (sample.isEmpty()) return replacement;
        if (sample.equals(sample.toUpperCase(Locale.US)) && sample.matches(".*[A-Z].*")) {
            return replacement.toUpperCase(Locale.US);
        }
        String letters = sample.replaceAll("[^A-Za-z]", "");
        if (!letters.isEmpty() && letters.equals(letters.toLowerCase(Locale.US))) return replacement;
        String[] sampleWords = sample.split(" ");
        String[] replWords = replacement.split(" ");
        boolean titled = sampleWords.length == replWords.length && sampleWords.length > 0;
        if (titled) {
            for (String word : sampleWords) {
                if (!word.isEmpty() && Character.isLetter(word.charAt(0)) && !Character.isUpperCase(word.charAt(0))) {
                    titled = false;
                    break;
                }
            }
        }
        if (titled) {
            StringBuilder builder = new StringBuilder();
            for (int i = 0; i < replWords.length; i++) {
                if (i > 0) builder.append(' ');
                String word = replWords[i];
                if (word.isEmpty()) continue;
                builder.append(Character.toUpperCase(word.charAt(0)));
                if (word.length() > 1) builder.append(word.substring(1));
            }
            return builder.toString();
        }
        if (Character.isUpperCase(sample.charAt(0)) && !replacement.isEmpty()) {
            return Character.toUpperCase(replacement.charAt(0)) + replacement.substring(1);
        }
        return replacement;
    }

    private static String canonFromSample(String sample, String expanded) {
        if (sample.equals(sample.toUpperCase(Locale.US)) && sample.matches(".*[A-Z].*")) {
            return expanded.toLowerCase(Locale.US);
        }
        if (!sample.isEmpty() && !expanded.isEmpty()
                && Character.isUpperCase(sample.charAt(0))
                && Character.isUpperCase(expanded.charAt(0))
                && !expanded.startsWith("I")) {
            return Character.toLowerCase(expanded.charAt(0)) + expanded.substring(1);
        }
        return expanded;
    }

    private static Pattern phrase(String value) {
        return Pattern.compile("(?<!\\w)" + Pattern.quote(value) + "(?!\\w)", Pattern.CASE_INSENSITIVE);
    }

    private static boolean isSpace(char value) {
        return value == ' ' || value == '\t' || value == '\n';
    }

    private static JSONObject empty() {
        JSONObject data = new JSONObject();
        try {
            data.put("version", 1);
            data.put("lessons", new JSONObject());
        } catch (Exception ignored) {
        }
        return data;
    }

    private static JSONObject load() {
        if (file == null || !file.exists()) return empty();
        try {
            ByteArrayOutputStream buffer = new ByteArrayOutputStream();
            try (FileInputStream input = new FileInputStream(file)) {
                byte[] piece = new byte[4096];
                int count;
                while ((count = input.read(piece)) >= 0) buffer.write(piece, 0, count);
            }
            JSONObject data = new JSONObject(buffer.toString(StandardCharsets.UTF_8.name()));
            if (data.optJSONObject("lessons") == null) data.put("lessons", new JSONObject());
            return data;
        } catch (Exception ex) {
            return empty();
        }
    }

    private static void save(JSONObject data) {
        if (file == null) return;
        File folder = file.getParentFile();
        if (folder != null && !folder.exists()) folder.mkdirs();
        File temporary = new File(file.getParentFile(), "brain.json.tmp");
        try (FileOutputStream output = new FileOutputStream(temporary)) {
            output.write(data.toString(2).getBytes(StandardCharsets.UTF_8));
        } catch (Exception ex) {
            return;
        }
        if (file.exists() && !file.delete()) return;
        if (!temporary.renameTo(file)) {
            temporary.delete();
        }
    }
}
