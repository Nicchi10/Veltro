package app.models;

import java.util.List;
import java.util.Map;

enum Role {
    SYSTEM,
    USER
}

interface Validator {
    boolean validate(String value);
}

abstract class Base {
    abstract void run();
}

class Session extends Base implements Validator {
    String token;
    User user;
    Integer expires = null;
    private String secret;
    List<String> tags;
    static int count;

    public boolean active() {
        return true;
    }

    public void refresh(int ttl) {
    }

    public static Session make(Map<String, Object> raw) {
        return new Session();
    }

    public boolean validate(String value) {
        return true;
    }
}

class User {
    String name;
}
