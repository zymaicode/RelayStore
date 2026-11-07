package core

import (
	"errors"
	"fmt"
	"strconv"
	"strings"
	"unicode"
)

// Node is a parsed Valve KeyValues tree (text VDF).
type Node struct {
	Key      string
	Value    string
	Children []*Node
}

func (n *Node) Child(key string) *Node {
	for _, c := range n.Children {
		if strings.EqualFold(c.Key, key) {
			return c
		}
	}
	return nil
}

func (n *Node) Path(keys ...string) *Node {
	cur := n
	for _, k := range keys {
		if cur == nil {
			return nil
		}
		cur = cur.Child(k)
	}
	return cur
}

type vdfParser struct {
	tokens []string
	pos    int
}

func tokenizeVDF(text string) ([]string, error) {
	var tokens []string
	i := 0
	n := len(text)
	for i < n {
		ch := text[i]
		switch {
		case ch == '/' && i+1 < n && text[i+1] == '/':
			for i < n && text[i] != '\n' {
				i++
			}
		case unicode.IsSpace(rune(ch)):
			i++
		case ch == '{' || ch == '}':
			tokens = append(tokens, string(ch))
			i++
		case ch == '"':
			i++
			var sb strings.Builder
			for i < n {
				if text[i] == '\\' && i+1 < n {
					sb.WriteByte(text[i+1])
					i += 2
					continue
				}
				if text[i] == '"' {
					break
				}
				sb.WriteByte(text[i])
				i++
			}
			if i >= n {
				return nil, errors.New("unterminated string")
			}
			i++
			tokens = append(tokens, sb.String())
		default:
			start := i
			for i < n && !unicode.IsSpace(rune(text[i])) && text[i] != '{' && text[i] != '}' && text[i] != '"' {
				i++
			}
			tokens = append(tokens, text[start:i])
		}
	}
	return tokens, nil
}

func (p *vdfParser) parseBlock(parent *Node) error {
	for p.pos < len(p.tokens) {
		token := p.tokens[p.pos]
		if token == "}" {
			p.pos++
			return nil
		}
		if p.pos+1 >= len(p.tokens) {
			return fmt.Errorf("dangling key %q", token)
		}
		next := p.tokens[p.pos+1]
		if next == "{" {
			child := &Node{Key: token}
			parent.Children = append(parent.Children, child)
			p.pos += 2
			if err := p.parseBlock(child); err != nil {
				return err
			}
			continue
		}
		child := &Node{Key: token, Value: next}
		parent.Children = append(parent.Children, child)
		p.pos += 2
	}
	return nil
}

func ParseVDF(text string) (*Node, error) {
	tokens, err := tokenizeVDF(text)
	if err != nil {
		return nil, err
	}
	root := &Node{}
	parser := &vdfParser{tokens: tokens}
	if err := parser.parseBlock(root); err != nil {
		return nil, err
	}
	return root, nil
}

func atoiSafe(s string) int {
	v, err := strconv.Atoi(strings.TrimSpace(s))
	if err != nil {
		return 0
	}
	return v
}

func atoi64Safe(s string) int64 {
	v, err := strconv.ParseInt(strings.TrimSpace(s), 10, 64)
	if err != nil {
		return 0
	}
	return v
}
